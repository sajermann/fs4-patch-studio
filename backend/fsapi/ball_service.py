"""Balls screen: the pack files the user sends, thumbnails, 3D preview and the zip balls are shared in.

Zip format (one ball or many), only the manifest and the files it names, side by side at the root of the zip:

    manifest.json   {"type": "fs4-ball", "version": 1, "ball": {...}}
                    {"type": "fs4-balls", "version": 1, "balls": [{...}, ...]}
    each ball:      {"name", "credits", "hidden", "mesh", "texture", "thumbnail", "created_at", "updated_at"}
                    mesh / texture / thumbnail = names of files in the zip (any name on upload; ball-<uid>.rx3,
                    ball-<uid>_textures.rx3, ball-<uid>.<ext> on download)
                    created_at / updated_at: when the entry was created and last changed in the project it came
                    from (ISO 8601; kept on import, null when unknown)
                    uid / original_id: the entry's uid (kept on import: the same entry imported again replaces it)
                    and the game's entry it edits (null = a new one); zips without them come in as new entries
                    on download every key is there, null when empty (credits, a missing file); on upload a key
                    may be null, "" or left out

The game id is not in the zip (each project gives its own), nor the stadiums using the ball. Files are shared as the
user sent them. A ball whose files are missing or not usable comes in without them (the screen shows what is
missing), never refused as a whole; a newer version than the app knows is refused.
"""
import hashlib
import io
import json
import os
import uuid
import zipfile

from PIL import Image

from fsmod import balls, gltf, model

from .project_store import IMAGE_EXTENSIONS, file_slug
from .share_service import kept_original, kept_uid

MANIFEST = 'manifest.json'
ONE, MANY = 'fs4-ball', 'fs4-balls'
VERSION = 1  # zip format; bump when its layout changes (older ones are read, newer ones refused)
MAX_ZIP = 2 * 1024 ** 3  # uncompressed bytes of an import
MAX_THUMBNAIL = 5 * 1024 * 1024
THUMB_WIDTH = 256
WEBP_QUALITY = 90


class BallZipError(ValueError):
    """A zip that cannot be imported at all; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


class BallService:
    def __init__(self, game, cache_root):
        self.game = game
        self.converter = balls.Converter(game)
        self.cache = os.path.join(cache_root, 'balls')

    # ---------------------------------------------------------------- files
    def check(self, kind, data):
        """Raises balls.BallError when `data` is not a usable pack file of that kind ('mesh' or 'texture')."""
        (balls.check_mesh if kind == 'mesh' else balls.check_texture)(data)

    def check_thumbnail(self, filename, data):
        ext = os.path.splitext(filename or '')[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            raise balls.BallError('ball_thumbnail_invalid', ext)
        if len(data) > MAX_THUMBNAIL:
            raise balls.BallError('ball_thumbnail_too_big')
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception as e:  # noqa: BLE001
            raise balls.BallError('ball_thumbnail_invalid', str(e)) from e

    def converted(self, mesh, texture):
        """(mesh, textures) RX3b of the user's files; raises balls.BallError."""
        return self.converter.converted(mesh, texture)

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

    def game_thumbnail(self, ball_id):
        """WebP of one of the game's balls (drawn from its files once, then cached)."""
        def make():
            return balls.thumbnail(*balls.game_files(self.game, ball_id), THUMB_WIDTH)
        return self._cached(f'game-{ball_id}-{self._originals_key()}', make)

    def thumbnail(self, mesh=None, texture=None, image=None):
        """WebP for the lists: the user's picture made small, or the ball drawn from its files."""
        if image is not None:
            key = 'img-' + hashlib.sha1(image).hexdigest()

            def make():
                img = Image.open(io.BytesIO(image)).convert('RGBA')
                img.thumbnail((THUMB_WIDTH, THUMB_WIDTH))
                return img
        else:
            key = 'ball-' + hashlib.sha1(hashlib.sha1(mesh).digest() + hashlib.sha1(texture).digest()).hexdigest()

            def make():
                return balls.thumbnail(*self.converted(mesh, texture), THUMB_WIDTH)
        return self._cached(key, make)

    @staticmethod
    def _glb(mesh_rx3b):
        return gltf.write_glb([balls.glb_mesh(mesh_rx3b)])

    @staticmethod
    def _png(textures_rx3b):
        buf = io.BytesIO()
        balls.color_image(textures_rx3b).save(buf, format='PNG')
        return buf.getvalue()

    def glb(self, mesh, texture):
        """GLB (node 'ball') of the converted ball, as the game will show it."""
        return self._glb(self.converted(mesh, texture)[0])

    def color_png(self, mesh, texture):
        return self._png(self.converted(mesh, texture)[1])

    def game_glb(self, ball_id):
        return self._glb(balls.game_files(self.game, ball_id)[0])

    def game_png(self, ball_id):
        return self._png(balls.game_files(self.game, ball_id)[1])

    # ---------------------------------------------------------------- zip
    def read_zip(self, source, save_ball_file, save_image):
        """(kind, [Ball JSON], [problem]) of a zip: kind 'one' or 'many'; each ball gets a new uid and its files are
        stored as provisional uploads (save_ball_file / save_image(file name, bytes) -> project path). A problem is
        {'index', 'name', 'field', 'code'}: the ball comes in without that file."""
        try:
            z = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as e:
            raise BallZipError('not_a_zip', str(e))
        with z:
            entries = {}
            for info in z.infolist():
                name = info.filename
                if info.is_dir() or '/' in name.rstrip('/') or '\\' in name or name.startswith('.') or ':' in name:
                    raise BallZipError('zip_not_flat', name)
                entries[name] = info
            if MANIFEST not in entries:
                raise BallZipError('no_manifest')
            if sum(i.file_size for i in entries.values()) > MAX_ZIP:
                raise BallZipError('zip_too_big')
            try:
                manifest = json.loads(z.read(MANIFEST).decode('utf-8'))
            except (ValueError, UnicodeDecodeError) as e:
                raise BallZipError('invalid_manifest', str(e))
            if not isinstance(manifest, dict) or manifest.get('type') not in (ONE, MANY):
                raise BallZipError('invalid_manifest', 'type')
            version = manifest.get('version')
            if not isinstance(version, int) or version < 1:
                raise BallZipError('invalid_manifest', 'version')
            if version > VERSION:
                raise BallZipError('zip_too_new', str(version))
            kind = 'one' if manifest['type'] == ONE else 'many'
            items = [manifest.get('ball')] if kind == 'one' else manifest.get('balls')
            if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
                raise BallZipError('invalid_manifest', 'balls')
            out, problems, stored = [], [], {}

            def stored_file(field, filename):
                """Project path of a file of the zip (one stored copy per file and kind), or a problem code."""
                if not isinstance(filename, str) or not filename:
                    return None, None
                if filename not in entries or filename == MANIFEST:
                    return None, 'ball_zip_file_missing'
                if (field, filename) in stored:
                    return stored[field, filename]
                data = z.read(entries[filename])
                try:
                    if field == 'thumbnail':
                        self.check_thumbnail(filename, data)
                        result = save_image(filename, data), None
                    else:
                        self.check(field, data)
                        result = save_ball_file(filename, data), None
                except balls.BallError as e:
                    result = None, e.code
                stored[field, filename] = result
                return result

            seen, valid = set(), set(balls.game_ids(self.game))
            for k, item in enumerate(items):
                name = item.get('name') if isinstance(item.get('name'), str) else ''
                credits = item.get('credits') if isinstance(item.get('credits'), str) else None
                ball = {'uid': kept_uid(item.get('uid'), 'a', seen),
                        'original_id': kept_original(item.get('original_id'), valid),
                        'name': name.strip(), 'credits': credits or None,
                        'hidden': item.get('hidden') is True,
                        'created_at': model.iso_date(item.get('created_at')),
                        'updated_at': model.iso_date(item.get('updated_at'))}
                for field in ('mesh', 'texture', 'thumbnail'):
                    path, problem = stored_file(field, item.get(field))
                    if path:
                        ball[field] = path
                    if problem:
                        problems.append({'index': k, 'name': name, 'field': field, 'code': problem})
                out.append(model.Ball.model_validate(ball).model_dump(mode='json', exclude_none=True))
        return kind, out, problems

    def write_zip(self, project_balls, folder, out, many):
        """Zip of saved balls (new ones, and edited game balls with files of their own) into the binary file `out`:
        their files as the user sent them, named after the ball's uid."""
        items = []
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for b in project_balls:
                stem = f'ball-{file_slug(b.uid)}'
                # every key is written, null when empty, so whoever edits the manifest by hand sees all of them
                item = {'uid': b.uid, 'original_id': b.original_id,
                        'name': b.name, 'credits': b.credits or None, 'hidden': b.hidden,
                        'created_at': b.created_at, 'updated_at': b.updated_at,
                        'mesh': None, 'texture': None, 'thumbnail': None}
                for field, name in (('mesh', f'{stem}.rx3'), ('texture', f'{stem}_textures.rx3'),
                                    ('thumbnail', stem + os.path.splitext(b.thumbnail or '')[1].lower())):
                    relative = getattr(b, field)
                    path = os.path.join(folder, relative) if relative else None
                    if path and os.path.isfile(path):
                        z.write(path, name)
                        item[field] = name
                items.append(item)
            manifest = ({'type': MANY, 'version': VERSION, 'balls': items} if many
                        else {'type': ONE, 'version': VERSION, 'ball': items[0]})
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
