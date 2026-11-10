"""Leagues, teams and players shared in a zip ("send me your team"): each entry goes alone, with its own files and the
links it keeps, never the entries it points to.

Zip format, only the manifest and the files it names, side by side at the root of the zip:

    manifest.json   one entry:  {"type": "fs4-league" | "fs4-team" | "fs4-player", "version": 1, "league": {...}}
                                (the key is the kind: "league", "team" or "player")
                    several:    {"type": "fs4-leagues" | "fs4-teams" | "fs4-players", "version": 1, "leagues": [...]}
                                (the key is the kind: "leagues", "teams" or "players")
                    (zips made on 09/11/2026 before this layout, with "items": [...], are still read)
    each item:      the entry as the project keeps it (every key, null when empty), with:
                    - its image fields (league image / wide_image, team crest and real kit pictures, player photo)
                      naming files of the zip (league-<uid>.png, team-<uid>-crest.png, player-<uid>.jpg...);
                    - a player with a real face: "face_files" = {path inside the face folder: file of the zip};
                    - the ids the build gives (league_id, team_id, player_id) left null: each project gives its own.

What each entry keeps (and the importing project resolves): a team its leagues, captain, set-piece takers and
lineups; a player his teams (number and position), boots and glove. An edited game entry (original_id) goes edited
and takes the place of that game entry where it is imported. Uids are kept, so an entry imported again (or a player
whose team was imported first) finds the same one. Files are shared as the user sent them.

Importing is two steps: inspect() reads the zip into a staging folder and tells what it holds (nothing in the project
changes), apply() puts the chosen entries' files into the project (images as uploads, face files in faces/<uid>/) and
returns the entries for the client to merge and save.
"""
import io
import json
import os
import re
import shutil
import time
import uuid
import zipfile

from PIL import Image

from fsmod import model, scanface

from .project_store import IMAGE_EXTENSIONS, file_slug

MANIFEST = 'manifest.json'
VERSION = 1  # zip format; bump when its layout changes (older ones are read, newer ones refused)
MAX_ZIP = 2 * 1024 ** 3  # uncompressed bytes of an import
MAX_IMAGE = 30 * 1024 * 1024
MAX_FACE_FILE = 64 * 1024 * 1024
STAGING_TTL = 24 * 3600  # seconds an inspected zip waits for apply()

KINDS = {'leagues': model.League, 'teams': model.Team, 'players': model.Player}
ONE = {'leagues': 'league', 'teams': 'team', 'players': 'player'}  # key (and type fs4-<key>) of a zip with one entry
LEGACY_ITEMS = 'items'  # key of the first layout (any number of entries under the plural type)
GAME_IDS = {'leagues': 'league_id', 'teams': 'team_id', 'players': 'player_id'}
FACE_FILES = 'face_files'
UID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')  # project uids (folder names)


def kept_uid(value, prefix, seen):
    """The uid an entry of a shared zip brings (kept, so importing it again finds the same entry), or a new one with
    `prefix` when it brings none, an invalid one or one already used in the same zip; added to `seen`."""
    uid = value if isinstance(value, str) and UID.match(value) and value not in seen else prefix + uuid.uuid4().hex[:12]
    seen.add(uid)
    return uid


def kept_original(value, valid):
    """The game entry (original_id) an edited entry of a shared zip names, when the game has it; else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value in valid else None


class ShareZipError(ValueError):
    """A zip that cannot be imported at all; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def image_slots(kind, entry):
    """(path in the entry JSON as a tuple of keys, zip file stem) of every image of an entry (JSON dict)."""
    uid = file_slug(entry.get('uid') or '')
    if kind == 'leagues':
        yield ('image',), f'league-{uid}'
        yield ('wide_image',), f'league-{uid}-wide'
    elif kind == 'teams':
        yield ('crest',), f'team-{uid}-crest'
        for slot, real in (entry.get('real_kits') or {}).items():
            if isinstance(real, dict):
                for part in model.REAL_KIT_FILES:
                    yield ('real_kits', slot, part), f'team-{uid}-{slot}-{part}'
    else:
        yield ('photo',), f'player-{uid}'


def _get(data, path):
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _set(data, path, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


def face_paths(source_id):
    """Paths a face's files may have inside its project folder (scanface.FILES with the pack id)."""
    return {f.format(source_id) for f in scanface.FILES.values()}


class ShareService:
    def __init__(self, cache_root):
        self.staging = os.path.join(cache_root, 'imports')

    # ---------------------------------------------------------------- export
    def write_zip(self, kind, entries, folder, out, many=False):
        """Zip of saved entries (model objects of one kind) into the binary file `out`: one entry in the one-entry
        layout unless `many`."""
        items = []
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for entry in entries:
                item = entry.model_dump(mode='json')  # every key, null when empty
                item[GAME_IDS[kind]] = None
                for path, stem in list(image_slots(kind, item)):
                    relative = _get(item, path)
                    full = os.path.join(folder, *relative.split('/')) if isinstance(relative, str) and relative else None
                    if full and os.path.isfile(full):
                        name = stem + os.path.splitext(full)[1].lower()
                        z.write(full, name)
                        _set(item, path, name)
                    elif relative:
                        _set(item, path, None)
                if kind == 'players':
                    item[FACE_FILES] = self._write_face(z, entry, folder)
                items.append(item)
            if many or len(items) != 1:
                manifest = {'type': f'fs4-{kind}', 'version': VERSION, kind: items}
            else:
                manifest = {'type': f'fs4-{ONE[kind]}', 'version': VERSION, ONE[kind]: items[0]}
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))

    @staticmethod
    def _write_face(z, player, folder):
        if player.face is None:
            return None
        base = scanface.project_face_dir(folder, player.uid)
        files = {}
        for n, relative in enumerate(sorted(face_paths(player.face.source_id))):
            full = os.path.join(base, *relative.split('/'))
            if os.path.isfile(full):
                name = f'player-{file_slug(player.uid)}-face-{n}{os.path.splitext(relative)[1]}'
                z.write(full, name)
                files[relative] = name
        return files or None

    # ---------------------------------------------------------------- import
    def _clean_staging(self):
        if not os.path.isdir(self.staging):
            return
        limit = time.time() - STAGING_TTL
        for name in os.listdir(self.staging):
            path = os.path.join(self.staging, name)
            try:
                if os.path.getmtime(path) < limit:
                    os.remove(path)
            except OSError:
                pass

    def _staged(self, token):
        if not token or not all(c in '0123456789abcdef' for c in token) or len(token) != 32:
            raise ShareZipError('import_expired')
        path = os.path.join(self.staging, f'{token}.zip')
        if not os.path.isfile(path):
            raise ShareZipError('import_expired')
        return path

    def inspect(self, kind, source):
        """Reads a zip of `kind` into the staging folder. Returns {'token', 'items': [entry JSON with zip file names],
        'problems': [{'index', 'name', 'field', 'code'}]}: an item whose file is missing or not usable comes in without
        it; an item that is not an entry of that kind is left out (code 'invalid_item')."""
        self._clean_staging()
        os.makedirs(self.staging, exist_ok=True)
        token = uuid.uuid4().hex
        path = os.path.join(self.staging, f'{token}.zip')
        with open(path, 'wb') as f:
            shutil.copyfileobj(source, f)
        try:
            items, problems = self._read(kind, path, store=None)
        except Exception:
            os.remove(path)
            raise
        return {'token': token, 'items': items, 'problems': problems}

    def apply(self, kind, token, uids, folder, save_image, as_uids=None):
        """The entries `uids` of an inspected zip, their files put into the project: images as provisional uploads
        (save_image(file name, bytes) -> project path) and a real face's files in faces/<uid>/. as_uids = {uid in the
        zip: uid it takes in the project} (the zip uploaded on an entry's page fills that entry, which keeps its uid).
        The staged zip is then dropped. Returns [entry JSON] ready for the project."""
        path = self._staged(token)

        cleared = set()

        def store(item, field, filename, data):
            if field == FACE_FILES:
                base = scanface.project_face_dir(folder, item['uid'])
                if item['uid'] not in cleared:  # the face replaces whatever the player had
                    cleared.add(item['uid'])
                    shutil.rmtree(base, ignore_errors=True)
                target = os.path.join(base, *filename.split('/'))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as f:
                    f.write(data)
                return filename
            return save_image(filename, data)

        wanted = set(uids)
        items, _ = self._read(kind, path, store=store, wanted=wanted, as_uids=as_uids)
        os.remove(path)
        return items

    def _read(self, kind, path, store, wanted=None, as_uids=None):
        """(items, problems) of a staged zip. With `store`, the files of the items in `wanted` are stored
        (store(item, field, name, bytes) -> value for the field) and their face folders replaced."""
        cls = KINDS[kind]
        try:
            z = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            raise ShareZipError('not_a_zip', str(e))
        with z:
            entries = {}
            for info in z.infolist():
                name = info.filename
                if info.is_dir() or '/' in name.rstrip('/') or '\\' in name or name.startswith('.') or ':' in name:
                    raise ShareZipError('zip_not_flat', name)
                entries[name] = info
            if MANIFEST not in entries:
                raise ShareZipError('no_manifest')
            if sum(i.file_size for i in entries.values()) > MAX_ZIP:
                raise ShareZipError('zip_too_big')
            try:
                manifest = json.loads(z.read(MANIFEST).decode('utf-8'))
            except (ValueError, UnicodeDecodeError) as e:
                raise ShareZipError('invalid_manifest', str(e))
            types = {f'fs4-{k}': k for k in KINDS} | {f'fs4-{ONE[k]}': k for k in KINDS}
            if not isinstance(manifest, dict) or manifest.get('type') not in types:
                raise ShareZipError('invalid_manifest', 'type')
            if types[manifest['type']] != kind:
                raise ShareZipError('wrong_kind', manifest['type'])
            version = manifest.get('version')
            if not isinstance(version, int) or version < 1:
                raise ShareZipError('invalid_manifest', 'version')
            if version > VERSION:
                raise ShareZipError('zip_too_new', str(version))
            if manifest['type'] == f'fs4-{ONE[kind]}':
                raw = [manifest.get(ONE[kind])]
            else:
                raw = manifest.get(kind, manifest.get(LEGACY_ITEMS))
            if not isinstance(raw, list) or not all(isinstance(i, dict) for i in raw):
                raise ShareZipError('invalid_manifest', 'items')

            out, problems, seen = [], [], set()
            for k, item in enumerate(raw):
                item = dict(item)
                label = self._label(kind, item)
                uid = item.get('uid')
                if not isinstance(uid, str) or not UID.match(uid) or uid in seen:
                    problems.append({'index': k, 'name': label, 'field': 'uid', 'code': 'invalid_item'})
                    continue
                seen.add(uid)
                keep = wanted is None or uid in wanted
                target = (as_uids or {}).get(uid)
                if keep and target is not None:
                    if not isinstance(target, str) or not UID.match(target):
                        raise ShareZipError('invalid_target_uid', str(target))
                    item['uid'] = target
                face_files = item.pop(FACE_FILES, None)
                item[GAME_IDS[kind]] = None
                for field_path, _ in list(image_slots(kind, item)):
                    name = _get(item, field_path)
                    if name in (None, ''):
                        _set(item, field_path, None)
                        continue
                    data, code = self._file(z, entries, name, MAX_IMAGE)
                    if code is None:
                        code = self._check_image(name, data)
                    if code:
                        problems.append({'index': k, 'name': label, 'field': '.'.join(field_path), 'code': code})
                        _set(item, field_path, None)
                    elif store and keep:
                        _set(item, field_path, store(item, 'image', name, data))
                try:
                    entry = cls.model_validate(item)
                except ValueError as e:
                    problems.append({'index': k, 'name': label, 'field': None, 'code': 'invalid_item',
                                     'detail': str(e)[:500]})
                    continue
                if kind == 'players' and entry.face is not None:
                    self._face(z, entries, entry, face_files, problems, k, label, store if keep else None)
                if keep:
                    out.append(entry.model_dump(mode='json', exclude_none=True))
        return out, problems

    def _face(self, z, entries, player, face_files, problems, k, label, store):
        """Checks (and with `store`, writes) a player's face files; a face without its files is dropped."""
        allowed = face_paths(player.face.source_id)
        files = {}
        if isinstance(face_files, dict):
            for relative, name in face_files.items():
                if relative not in allowed or not isinstance(name, str):
                    continue
                data, code = self._file(z, entries, name, MAX_FACE_FILE)
                if code:
                    problems.append({'index': k, 'name': label, 'field': 'face', 'code': code})
                else:
                    files[relative] = data
        required = {scanface.FILES[r].format(player.face.source_id) for r in scanface.REQUIRED}
        if not required <= set(files):
            problems.append({'index': k, 'name': label, 'field': 'face', 'code': 'face_files_missing'})
            player.face = None
            player.generic = True
            return
        if store:
            for relative, data in files.items():
                store({'uid': player.uid}, FACE_FILES, relative, data)

    @staticmethod
    def _file(z, entries, name, limit):
        if not isinstance(name, str) or name not in entries or name == MANIFEST:
            return None, 'zip_file_missing'
        if entries[name].file_size > limit:
            return None, 'zip_file_too_big'
        return z.read(entries[name]), None

    @staticmethod
    def _check_image(name, data):
        if os.path.splitext(name)[1].lower() not in IMAGE_EXTENSIONS:
            return 'image_invalid'
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception:  # noqa: BLE001
            return 'image_invalid'
        return None

    @staticmethod
    def _label(kind, item):
        if kind == 'players':
            text = item.get('display_name') or f"{item.get('first_name') or ''} {item.get('last_name') or ''}".strip()
        else:
            text = item.get('name')
        return text if isinstance(text, str) else ''
