"""The user's project on disk: <project_dir>/database.json + images/ + faces/ + boots/ + gloves/ + balls/.

The JSON is the only source of truth of the app; it is never deduced from game files.
Images, boot, glove and ball files: an upload gets a provisional name (UPLOAD_PREFIX) and keeps it while the project is not
saved, so "Discard" can go back to the previous file; saving gives every file the fixed name of its entity
(image_fields, boot_file_fields, glove_file_fields, ball_file_fields) and deletes the images, faces and pack files nothing
uses any more. Files are kept
as the user sent them (conversions only happen for the preview and the patch), except images bigger than what the
patch can use (image_limit: team crests over fsmod.crest.MAX_SOURCE, league images over fsmod.leaguelogo.SOURCE_MIN,
real kit images over fsmod.kit.REAL_SOURCE_MAX):
saving reduces them (PNG), and opening a project of an older version does it once (upgrade). The game never draws
them bigger, and huge sources made every build slow.
"""
import hashlib
import io
import json
import os
import re
import shutil
import uuid
import zipfile

from PIL import Image

from fsmod import crest, kit, leaguelogo, model, scanface

PROJECT_FILE = 'database.json'
LEGACY_PROJECT_FILE = 'projeto.json'  # name used before 24/10/2026, renamed on start (upgrade)
IMAGES_DIR = 'images'
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
BOOTS_DIR = 'boots'  # the pack files of the project's boots (boot-<uid>.rx3, boot-<uid>_textures.rx3)
BOOT_EXTENSION = '.rx3'
GLOVES_DIR = 'gloves'  # the pack files of the project's gloves (glove-<uid>_textures.rx3)
BALLS_DIR = 'balls'  # the pack files of the project's balls (ball-<uid>.rx3, ball-<uid>_textures.rx3)
UPLOAD_PREFIX = 'upload-'  # provisional name of an upload until the project is saved
BACKUP_MAX_BYTES = 2 * 1024 ** 3  # uncompressed size accepted when restoring a backup zip


class ProjectFileError(ValueError):
    """database.json exists but cannot be opened; `code` names the reason (texts in the API): project_unreadable
    (not JSON / not UTF-8 / no permission), project_too_new (saved by a newer version of the app),
    project_invalid (JSON that is not a project)."""

    def __init__(self, code, path, detail):
        super().__init__(f'{code}: {path}: {detail}')
        self.code, self.path, self.detail = code, path, detail


class BackupError(ValueError):
    """A backup zip that cannot be restored; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def file_slug(text):
    """Text for a file name: runs of spaces become '-', characters Windows forbids in file names are dropped."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', text or '').strip()
    return re.sub(r'\s+', '-', text).strip('-.')


def image_fields(project):
    """(entity, field, fixed path under images/ without extension) of every image slot of the project: one fixed
    name per entity and slot, in a folder per kind (leagues/, teams/, teams/kits/, players/)."""
    for lg in project.leagues:
        yield lg, 'image', f'leagues/league-{file_slug(lg.uid)}'
        yield lg, 'wide_image', f'leagues/league-{file_slug(lg.uid)}-wide'
    for tm in project.teams:
        yield tm, 'crest', f'teams/team-{file_slug(tm.uid)}'
        for slot, real in tm.real_kits.items():  # teams/kits/team-<uid>-<slot>-<part>
            for part in model.REAL_KIT_FILES:
                yield real, part, f'teams/kits/team-{file_slug(tm.uid)}-{slot}-{part}'
    for pl in project.players:
        yield pl, 'photo', f'players/player-{file_slug(pl.uid)}'
    for b in project.boots:
        yield b, 'thumbnail', f'boots/boot-{file_slug(b.uid)}'
    for g in project.gloves:
        yield g, 'thumbnail', f'gloves/glove-{file_slug(g.uid)}'
    for b in project.balls:
        yield b, 'thumbnail', f'balls/ball-{file_slug(b.uid)}'


def image_limit(entity, field):
    """size -> reduced (width, height) or None, the biggest size the patch uses for this image slot (team crest:
    fsmod.crest; league images: fsmod.leaguelogo; real kit images: fsmod.kit), or None for slots kept as they are."""
    if field == 'crest' and isinstance(entity, model.Team):
        return crest.limited_size
    if field in ('image', 'wide_image') and isinstance(entity, model.League):
        return leaguelogo.limited_size
    if field in model.REAL_KIT_FILES and isinstance(entity, model.RealKit):
        return lambda size: kit.limited_size(field, size)
    return None


def oversized(path, limit):
    """True when the image at path is bigger than limit (image_limit) allows (unreadable files: False)."""
    try:
        with Image.open(path) as im:
            return limit(im.size) is not None
    except Exception:  # noqa: BLE001
        return False


def limited_image(data, limit):
    """PNG bytes of the image `data` reduced by limit (image_limit), or None when it already fits."""
    with Image.open(io.BytesIO(data)) as im:
        size = limit(im.size)
        if size is None:
            return None
        small = im.convert('RGBA').resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format='PNG')
    return buf.getvalue()


def boot_file_fields(project):
    """(boot, field, fixed file name under boots/) of every boot file slot of the project."""
    for b in project.boots:
        yield b, 'mesh', f'boot-{file_slug(b.uid)}{BOOT_EXTENSION}'
        yield b, 'texture', f'boot-{file_slug(b.uid)}_textures{BOOT_EXTENSION}'


def glove_file_fields(project):
    """(glove, field, fixed file name under gloves/) of every glove file slot of the project."""
    for g in project.gloves:
        yield g, 'texture', f'glove-{file_slug(g.uid)}_textures{BOOT_EXTENSION}'


def ball_file_fields(project):
    """(ball, field, fixed file name under balls/) of every ball file slot of the project."""
    for b in project.balls:
        yield b, 'mesh', f'ball-{file_slug(b.uid)}{BOOT_EXTENSION}'
        yield b, 'texture', f'ball-{file_slug(b.uid)}_textures{BOOT_EXTENSION}'


# folder -> slots of pack files
PACK_FILES = ((BOOTS_DIR, boot_file_fields), (GLOVES_DIR, glove_file_fields), (BALLS_DIR, ball_file_fields))


def migrate_folder(old, new):
    """Moves the project kept in `old` (layout before 24/10/2026: <repo>/projeto) into `new` when `new` has no
    project yet. Returns True when something was moved."""
    if os.path.abspath(old) == os.path.abspath(new) or not os.path.isdir(old):
        return False
    if not any(os.path.isfile(os.path.join(old, f)) for f in (PROJECT_FILE, LEGACY_PROJECT_FILE)):
        return False
    if ProjectStore(new).exists() or os.path.isfile(os.path.join(new, LEGACY_PROJECT_FILE)):
        return False
    os.makedirs(new, exist_ok=True)
    for name in os.listdir(old):
        if name != '.gitkeep':
            shutil.move(os.path.join(old, name), os.path.join(new, name))
    shutil.rmtree(old)
    return True


class ProjectStore:
    def __init__(self, folder):
        self.folder = folder

    @property
    def path(self):
        return os.path.join(self.folder, PROJECT_FILE)

    @property
    def images_dir(self):
        return os.path.join(self.folder, IMAGES_DIR)

    @property
    def boots_dir(self):
        return os.path.join(self.folder, BOOTS_DIR)

    @property
    def gloves_dir(self):
        return os.path.join(self.folder, GLOVES_DIR)

    def exists(self):
        return os.path.exists(self.path)

    def upgrade(self, migrate=None):
        """Brings a project saved by older versions of the app to the current layout: projeto.json becomes
        database.json, migrate(data) converts older contents (returns True when it changed something) and images get
        their fixed names and folders (orphans deleted). When migrate fails (e.g. no original files yet) the file is
        left as it is: saving it would drop what the current model no longer reads. Returns True when something
        changed."""
        legacy = os.path.join(self.folder, LEGACY_PROJECT_FILE)
        if not self.exists():
            if not os.path.isfile(legacy):
                return False
            os.replace(legacy, self.path)
        data = self._read_json()
        try:
            converted = bool(migrate and migrate(data))
        except Exception:  # noqa: BLE001 (converted later, when the project is opened)
            return False
        project = self._model(data)
        settled = all(not path or path == f'{IMAGES_DIR}/{stem}{os.path.splitext(path)[1].lower()}'
                      for path, stem in ((getattr(e, f), stem) for e, f, stem in image_fields(project)))
        if settled and not self._loose_images() and not converted and not self._oversized_images(project):
            return False
        self.save(project)
        return True

    def _oversized_images(self, project):
        """Images bigger than the patch uses (image_limit; stored by older versions of the app)."""
        out = []
        for entity, field, _ in image_fields(project):
            relative, limit = getattr(entity, field), image_limit(entity, field)
            if relative and limit:
                try:
                    path = self.image_path(relative)
                except ValueError:
                    continue
                if os.path.isfile(path) and oversized(path, limit):
                    out.append(path)
        return out

    def _loose_images(self):
        """Files left directly in images/ (old layout, abandoned uploads)."""
        if not os.path.isdir(self.images_dir):
            return []
        return [n for n in os.listdir(self.images_dir) if os.path.isfile(os.path.join(self.images_dir, n))
                and os.path.splitext(n)[1].lower() in IMAGE_EXTENSIONS | {'.tmp'}]

    def load(self, migrate=None):
        """Saved project (v1 files are converted to v2 in memory); empty project when there is none. migrate(data)
        may change the JSON before it is read (fsapi.main: original_player.absorb_game_links)."""
        if not self.exists():
            return model.Project()
        data = self._read_json()
        if migrate:
            migrate(data)
        return self._model(data)

    def _read_json(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:  # json.JSONDecodeError and UnicodeDecodeError are ValueErrors
            raise ProjectFileError('project_unreadable', self.path, f'{type(e).__name__}: {e}') from e
        if not isinstance(data, dict):
            raise ProjectFileError('project_invalid', self.path, 'not a JSON object')
        version = data.get('version')
        if isinstance(version, int) and version > model.CONTRACT_VERSION:
            raise ProjectFileError('project_too_new', self.path,
                                   f'contract v{version}, this version of the app reads up to v{model.CONTRACT_VERSION}')
        return data

    def _model(self, data):
        try:
            return model.load(data)
        except ValueError as e:  # pydantic.ValidationError
            raise ProjectFileError('project_invalid', self.path, str(e)) from e

    def save(self, project):
        """Writes the project, renaming its images to their fixed names (the project passed in is updated) and then
        deleting the images and faces it no longer uses."""
        os.makedirs(self.folder, exist_ok=True)
        self._settle_images(project)
        for sub, fields in PACK_FILES:
            self._settle_pack_files(project, sub, fields)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(project.to_json(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self._delete_unused(project)

    def _settle_images(self, project):
        """Copies every image the project uses to the fixed name of its slot and points the slot there. All sources
        are read first: one file may feed several slots (a copied team keeps the crest of the original) and be
        replaced by them."""
        pending = []
        for entity, field, stem in image_fields(project):
            relative = getattr(entity, field)
            if not relative:
                continue
            try:
                source = self.image_path(relative)
            except ValueError:
                continue
            if not os.path.isfile(source):
                continue
            with open(source, 'rb') as f:
                data, ext = f.read(), os.path.splitext(source)[1].lower()
            limit = image_limit(entity, field)
            if limit:
                try:
                    small = limited_image(data, limit)
                except Exception:  # noqa: BLE001 (an unreadable image is kept as it is)
                    small = None
                if small is not None:
                    data, ext = small, '.png'
            pending.append((entity, field, stem + ext, data))
        for entity, field, name, data in pending:
            target = os.path.join(self.images_dir, *name.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not (os.path.isfile(target) and os.path.getsize(target) == len(data) and _read(target) == data):
                tmp = target + '.tmp'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, target)
            setattr(entity, field, f'{IMAGES_DIR}/{name}')

    def _settle_pack_files(self, project, sub, fields):
        """Like _settle_images for the pack files of boots or gloves (sub = their folder, fields = boot_file_fields /
        glove_file_fields)."""
        folder = os.path.join(self.folder, sub)
        pending = []
        for entity, field, name in fields(project):
            relative = getattr(entity, field)
            if not relative:
                continue
            try:
                source = self._pack_file_path(sub, relative)
            except ValueError:
                continue
            if os.path.isfile(source):
                pending.append((entity, field, name, _read(source)))
        for entity, field, name, data in pending:
            target = os.path.join(folder, name)
            os.makedirs(folder, exist_ok=True)
            if not (os.path.isfile(target) and os.path.getsize(target) == len(data) and _read(target) == data):
                tmp = target + '.tmp'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, target)
            setattr(entity, field, f'{sub}/{name}')

    def _delete_unused(self, project):
        """Images (uploads included) and real-face folders that the saved project does not reference."""
        used = {os.path.normcase(os.path.join(self.folder, *getattr(e, f).split('/')))
                for e, f, _ in image_fields(project) if getattr(e, f)}
        for root, _, files in os.walk(self.images_dir):
            for name in files:
                path = os.path.join(root, name)
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTENSIONS | {'.tmp'} and os.path.normcase(path) not in used:
                    os.remove(path)
        for root, dirs, files in os.walk(self.images_dir, topdown=False):
            if root != self.images_dir and not os.listdir(root):
                os.rmdir(root)  # a kind folder left empty
        for sub, fields in PACK_FILES:
            used = {os.path.normcase(os.path.join(self.folder, *getattr(e, f).split('/')))
                    for e, f, _ in fields(project) if getattr(e, f)}
            folder = os.path.join(self.folder, sub)
            if os.path.isdir(folder):
                for name in os.listdir(folder):
                    path = os.path.join(folder, name)
                    if os.path.isfile(path) and os.path.normcase(path) not in used:
                        os.remove(path)
        faces = os.path.join(self.folder, scanface.PROJECT_DIR)
        with_face = {p.uid for p in project.players if p.face}
        if os.path.isdir(faces):
            for uid in os.listdir(faces):
                if uid not in with_face and os.path.isdir(os.path.join(faces, uid)):
                    shutil.rmtree(os.path.join(faces, uid))

    def content_hash(self):
        """Hash of the saved JSON plus the images and faces it references (detects changes not yet built; images
        keep their name when replaced, so their bytes count)."""
        if not self.exists():
            return None
        h = hashlib.sha1()
        with open(self.path, 'rb') as f:
            h.update(f.read())
        project = self.load()
        for entity, field, _ in image_fields(project):
            relative = getattr(entity, field)
            if relative:
                p = os.path.join(self.folder, relative)
                if os.path.isfile(p):
                    h.update(_read(p))
        for player in project.players:
            if not player.generic and player.face:
                files = scanface.read_files(scanface.project_face_dir(self.folder, player.uid), player.face.source_id)
                for kind in sorted(files):
                    h.update(files[kind])
        for _, fields in PACK_FILES:
            for entity, field, _ in fields(project):
                relative = getattr(entity, field)
                if relative and os.path.isfile(os.path.join(self.folder, relative)):
                    h.update(_read(os.path.join(self.folder, relative)))
        return h.hexdigest()

    def _save_pack_file(self, sub, data):
        name = f'{UPLOAD_PREFIX}{uuid.uuid4().hex[:12]}{BOOT_EXTENSION}'
        folder = os.path.join(self.folder, sub)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(data)
        return f'{sub}/{name}'

    def _pack_file_path(self, sub, relative):
        full = os.path.abspath(os.path.join(self.folder, relative))
        if not full.startswith(os.path.abspath(os.path.join(self.folder, sub)) + os.sep):
            raise ValueError(f'invalid {sub} file path')
        return full

    def save_boot_file(self, filename, data):
        """Stores an uploaded boot file (.rx3) under boots/ with a provisional name and returns its project-relative
        path; it gets the fixed name of its boot when the project is saved."""
        return self._save_pack_file(BOOTS_DIR, data)

    def boot_file_path(self, relative):
        """Absolute path of a project boot file, refusing anything outside boots/."""
        return self._pack_file_path(BOOTS_DIR, relative)

    def save_glove_file(self, filename, data):
        """Stores an uploaded glove file (.rx3) under gloves/ with a provisional name (like save_boot_file)."""
        return self._save_pack_file(GLOVES_DIR, data)

    def glove_file_path(self, relative):
        """Absolute path of a project glove file, refusing anything outside gloves/."""
        return self._pack_file_path(GLOVES_DIR, relative)

    def save_ball_file(self, filename, data):
        """Stores an uploaded ball file (.rx3) under balls/ with a provisional name (like save_boot_file)."""
        return self._save_pack_file(BALLS_DIR, data)

    def ball_file_path(self, relative):
        """Absolute path of a project ball file, refusing anything outside balls/."""
        return self._pack_file_path(BALLS_DIR, relative)

    def save_image(self, filename, data):
        """Stores an uploaded image under images/ with a provisional name and returns its project-relative path;
        the image gets the fixed name of its entity when the project is saved."""
        ext = os.path.splitext(os.path.basename(filename or 'image.png'))[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise ValueError(f'unsupported image type: {ext}')
        name = f'{UPLOAD_PREFIX}{uuid.uuid4().hex[:12]}{ext}'
        os.makedirs(self.images_dir, exist_ok=True)
        with open(os.path.join(self.images_dir, name), 'wb') as f:
            f.write(data)
        return f'{IMAGES_DIR}/{name}'

    def write_backup(self, out):
        """Zip of the whole project folder (database.json, images/, faces/, boots/, gloves/, balls/) into the binary file `out`."""
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            if self.exists():
                z.write(self.path, PROJECT_FILE)
            for sub in (IMAGES_DIR, scanface.PROJECT_DIR, BOOTS_DIR, GLOVES_DIR, BALLS_DIR):
                for root, _, files in os.walk(os.path.join(self.folder, sub)):
                    for name in files:
                        if not name.endswith('.tmp'):
                            full = os.path.join(root, name)
                            z.write(full, os.path.relpath(full, self.folder).replace(os.sep, '/'))

    def restore_backup(self, source):
        """Replaces the project folder with a backup zip (a path or a binary file). The zip may hold the folder's
        content or the folder itself; only database.json (or the old projeto.json), images/ and faces/ are taken.
        Everything is checked and extracted beside the folder first, so a bad zip leaves the project as it was."""
        try:
            z = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as e:
            raise BackupError('not_a_zip', str(e))
        with z:
            entries = [i for i in z.infolist() if not i.is_dir()]
            roots = [i.filename.rsplit('/', 1)[0] + '/' if '/' in i.filename else ''
                     for i in entries if i.filename.rsplit('/', 1)[-1] in (PROJECT_FILE, LEGACY_PROJECT_FILE)]
            if not roots:
                raise BackupError('no_database')
            prefix = min(roots, key=len)
            picked = []
            for info in entries:
                if not info.filename.startswith(prefix):
                    continue
                rel = info.filename[len(prefix):]
                parts = rel.split('/')
                if '..' in parts or rel.startswith('/') or ':' in rel or '\\' in rel:
                    raise BackupError('unsafe_path', info.filename)
                if rel in (PROJECT_FILE, LEGACY_PROJECT_FILE) or \
                        (len(parts) > 1 and parts[0] in (IMAGES_DIR, scanface.PROJECT_DIR, BOOTS_DIR, GLOVES_DIR, BALLS_DIR)):
                    picked.append((info, rel))
            if sum(i.file_size for i, _ in picked) > BACKUP_MAX_BYTES:
                raise BackupError('too_big')
            database = PROJECT_FILE if any(rel == PROJECT_FILE for _, rel in picked) else LEGACY_PROJECT_FILE
            picked = [(i, rel) for i, rel in picked if rel not in (PROJECT_FILE, LEGACY_PROJECT_FILE) or rel == database]
            try:
                model.load(json.loads(z.read(prefix + database).decode('utf-8')))
            except Exception as e:
                raise BackupError('invalid_database', str(e))
            folder = os.path.abspath(self.folder)
            staging, old = folder + '.restore', folder + '.old'
            for leftover in (staging, old):
                if os.path.isdir(leftover):
                    shutil.rmtree(leftover)
            os.makedirs(staging)
            try:
                for info, rel in picked:
                    target = os.path.join(staging, *rel.split('/'))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(info) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        try:
            if os.path.isdir(folder):
                os.replace(folder, old)
            os.replace(staging, folder)
        except OSError:
            if os.path.isdir(old) and not os.path.isdir(folder):
                os.replace(old, folder)  # put the project back (e.g. a file in use on Windows)
            shutil.rmtree(staging, ignore_errors=True)
            raise
        shutil.rmtree(old, ignore_errors=True)
        if not self.upgrade():
            self.save(self.load())  # fixed image names, nothing unused left

    def image_path(self, relative):
        """Absolute path of a project image, refusing anything outside images/."""
        full = os.path.abspath(os.path.join(self.folder, relative))
        if not full.startswith(os.path.abspath(self.images_dir) + os.sep):
            raise ValueError('invalid image path')
        return full


def _read(path):
    with open(path, 'rb') as f:
        return f.read()
