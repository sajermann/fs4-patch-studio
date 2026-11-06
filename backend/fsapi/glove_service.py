"""Gloves screen: the pack file the user sends, thumbnails, the 3D preview's texture and the zip gloves are shared in.

Zip format (one glove or many), only the manifest and the files it names, side by side at the root of the zip:

    manifest.json   {"type": "fs4-glove", "version": 1, "glove": {...}}
                    {"type": "fs4-gloves", "version": 1, "gloves": [{...}, ...]}
    each glove:     {"name", "credits", "hidden", "texture", "thumbnail"}
                    texture / thumbnail = names of files in the zip (any name on upload; glove-<uid>_textures.rx3,
                    glove-<uid>.<ext> on download)
                    on download every key is there, null when empty (credits, a missing file); on upload a key
                    may be null, "" or left out

The game code is not in the zip (each project gives its own). Files are shared as the user sent them. A glove whose
file is missing or not usable comes in without it (the screen shows what is missing), never refused as a whole;
a newer version than the app knows is refused.
"""
import hashlib
import io
import json
import os
import uuid
import zipfile

from PIL import Image

from fsmod import gloves, model, rx3tex

from .project_store import IMAGE_EXTENSIONS, file_slug

MANIFEST = 'manifest.json'
ONE, MANY = 'fs4-glove', 'fs4-gloves'
VERSION = 1  # zip format; bump when its layout changes (older ones are read, newer ones refused)
MAX_ZIP = 2 * 1024 ** 3  # uncompressed bytes of an import
MAX_THUMBNAIL = 5 * 1024 * 1024
THUMB_WIDTH = 256
WEBP_QUALITY = 90


class GloveZipError(ValueError):
    """A zip that cannot be imported at all; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


class GloveService:
    def __init__(self, game, cache_root):
        self.game = game
        self.converter = gloves.Converter(game)
        self.cache = os.path.join(cache_root, 'gloves')

    # ---------------------------------------------------------------- files
    def check(self, data):
        """Raises gloves.GloveError when `data` is not a usable pack glove file."""
        gloves.check_texture(data)

    def check_thumbnail(self, filename, data):
        ext = os.path.splitext(filename or '')[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise gloves.GloveError('glove_thumbnail_invalid', ext)
        if len(data) > MAX_THUMBNAIL:
            raise gloves.GloveError('glove_thumbnail_too_big')
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception as e:  # noqa: BLE001
            raise gloves.GloveError('glove_thumbnail_invalid', str(e)) from e

    # ---------------------------------------------------------------- pictures
    def _cached(self, key, make):
        path = os.path.join(self.cache, f'{key}.webp')
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                return f.read()
        img = make()
        buf = io.BytesIO()
        img.save(buf, format='WEBP', quality=WEBP_QUALITY)
        data = buf.getvalue()
        os.makedirs(self.cache, exist_ok=True)
        tmp = f'{path}.{uuid.uuid4().hex}.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
        return data

    def _originals_key(self):
        st = os.stat(self.game.target_path('data3.big'))
        return hashlib.sha1(f'{st.st_size}:{st.st_mtime_ns}'.encode()).hexdigest()[:10]

    def game_thumbnail(self, code):
        """WebP of one of the game's gloves (drawn from its files once, then cached)."""
        def make():
            return gloves.thumbnail(*gloves.game_files(self.game, code), THUMB_WIDTH)
        return self._cached(f'game-{code}-{self._originals_key()}', make)

    def thumbnail(self, texture=None, image=None):
        """WebP for the lists: the user's picture made small, or the glove drawn from its file."""
        if image is not None:
            key = 'img-' + hashlib.sha1(image).hexdigest()

            def make():
                img = Image.open(io.BytesIO(image)).convert('RGBA')
                img.thumbnail((THUMB_WIDTH, THUMB_WIDTH))
                return img
        else:
            key = 'glove-' + hashlib.sha1(texture).hexdigest()

            def make():
                color, _ = self.converter.converted(texture)
                return gloves.thumbnail(self.converter.template['mesh'], color, THUMB_WIDTH)
        return self._cached(key, make)

    def color_png(self, texture):
        """Color map of the user's glove as the game will show it (the 3D preview's texture)."""
        color, _ = self.converter.converted(texture)
        buf = io.BytesIO()
        rx3tex.to_image(color, rx3tex.textures(color)[0]).convert('RGB').save(buf, format='PNG')
        return buf.getvalue()

    # ---------------------------------------------------------------- zip
    def read_zip(self, source, save_glove_file, save_image):
        """(kind, [Glove JSON], [problem]) of a zip: kind 'one' or 'many'; each glove gets a new uid and its files are
        stored as provisional uploads (save_glove_file / save_image(file name, bytes) -> project path). A problem is
        {'index', 'name', 'field', 'code'}: the glove comes in without that file."""
        try:
            z = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as e:
            raise GloveZipError('not_a_zip', str(e))
        with z:
            entries = {}
            for info in z.infolist():
                name = info.filename
                if info.is_dir() or '/' in name.rstrip('/') or '\\' in name or name.startswith('.') or ':' in name:
                    raise GloveZipError('zip_not_flat', name)
                entries[name] = info
            if MANIFEST not in entries:
                raise GloveZipError('no_manifest')
            if sum(i.file_size for i in entries.values()) > MAX_ZIP:
                raise GloveZipError('zip_too_big')
            try:
                manifest = json.loads(z.read(MANIFEST).decode('utf-8'))
            except (ValueError, UnicodeDecodeError) as e:
                raise GloveZipError('invalid_manifest', str(e))
            if not isinstance(manifest, dict) or manifest.get('type') not in (ONE, MANY):
                raise GloveZipError('invalid_manifest', 'type')
            version = manifest.get('version')
            if not isinstance(version, int) or version < 1:
                raise GloveZipError('invalid_manifest', 'version')
            if version > VERSION:
                raise GloveZipError('zip_too_new', str(version))
            kind = 'one' if manifest['type'] == ONE else 'many'
            items = [manifest.get('glove')] if kind == 'one' else manifest.get('gloves')
            if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                raise GloveZipError('invalid_manifest', 'gloves')
            out, problems, stored = [], [], {}

            def stored_file(field, filename):
                """Project path of a file of the zip (one stored copy per file and kind), or a problem code."""
                if not isinstance(filename, str) or not filename:
                    return None, None
                if filename not in entries or filename == MANIFEST:
                    return None, 'glove_zip_file_missing'
                if (field, filename) in stored:
                    return stored[field, filename]
                data = z.read(entries[filename])
                try:
                    if field == 'thumbnail':
                        self.check_thumbnail(filename, data)
                        result = save_image(filename, data), None
                    else:
                        self.check(data)
                        result = save_glove_file(filename, data), None
                except gloves.GloveError as e:
                    result = None, e.code
                stored[field, filename] = result
                return result

            for k, item in enumerate(items):
                name = item.get('name') if isinstance(item.get('name'), str) else ''
                credits = item.get('credits') if isinstance(item.get('credits'), str) else None
                glove = {'uid': 'g' + uuid.uuid4().hex[:12], 'name': name.strip(), 'credits': credits or None,
                         'hidden': item.get('hidden') is True}
                for field in ('texture', 'thumbnail'):
                    path, problem = stored_file(field, item.get(field))
                    if path:
                        glove[field] = path
                    if problem:
                        problems.append({'index': k, 'name': name, 'field': field, 'code': problem})
                out.append(model.Glove.model_validate(glove).model_dump(mode='json', exclude_none=True))
        return kind, out, problems

    def write_zip(self, project_gloves, folder, out, many):
        """Zip of saved gloves (new ones, and edited game gloves with a file of their own) into the binary file `out`:
        their files as the user sent them, named after the glove's uid."""
        items = []
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for g in project_gloves:
                stem = f'glove-{file_slug(g.uid)}'
                # every key is written, null when empty, so whoever edits the manifest by hand sees all of them
                item = {'name': g.name, 'credits': g.credits or None, 'hidden': g.hidden,
                        'texture': None, 'thumbnail': None}
                for field, name in (('texture', f'{stem}_textures.rx3'),
                                    ('thumbnail', stem + os.path.splitext(g.thumbnail or '')[1].lower())):
                    relative = getattr(g, field)
                    path = os.path.join(folder, relative) if relative else None
                    if path and os.path.isfile(path):
                        z.write(path, name)
                        item[field] = name
                items.append(item)
            manifest = ({'type': MANY, 'version': VERSION, 'gloves': items} if many
                        else {'type': ONE, 'version': VERSION, 'glove': items[0]})
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
