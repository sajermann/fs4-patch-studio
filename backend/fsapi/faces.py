"""Real faces (FIFA 14-16 packs) for the player's Visual tab: the pack folders of the settings, a paged gallery of
all their faces, 3D preview, copy.

The packs stay where the user keeps them (read in place, never written); picking a face copies only that face's
files into the project (scanface.PROJECT_DIR/<player uid>/) and what the pack's manifest.json says about it (name,
credits) into the player. The 3D preview shows the face already converted (fsmod.scanface, ~3 s), so it is what the
game will draw; conversions are cached in memory, the packs' lists in memory until their folders change, and the
gallery thumbnails also on disk (<data dir>/cache/faces/thumbs).
"""
import hashlib
import logging
import os
import struct
import threading
import unicodedata
import uuid
from collections import OrderedDict

from fsmod import facepack, preview, scanface


log = logging.getLogger('fsapi')
UNSUPPORTED_MESSAGE = 'Esta face está em um formato que o app ainda não sabe converter.'


class FaceError(Exception):
    def __init__(self, code, message, status=400, error=None):
        super().__init__(message)
        self.code, self.message, self.status, self.error = code, message, status, error


def _unsupported(key, error):
    log.warning('face %s not converted: %s', key, error)
    return FaceError('face_unsupported', UNSUPPORTED_MESSAGE, 422, str(error) or type(error).__name__)


class _Lru:
    """Small LRU cache; concurrent requests for the same missing key wait for one make() (the 3D preview asks
    for 8 files of the same conversion at once)."""

    def __init__(self, size):
        self.size, self.items, self.lock = size, OrderedDict(), threading.Lock()
        self.pending = {}

    def get(self, key, make):
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
            key_lock = self.pending.setdefault(key, threading.Lock())
        with key_lock:
            with self.lock:
                if key in self.items:
                    return self.items[key]
            try:
                value = make()
            except BaseException:
                with self.lock:
                    self.pending.pop(key, None)
                raise
            with self.lock:
                self.items[key] = value
                while len(self.items) > self.size:
                    self.items.popitem(last=False)
                self.pending.pop(key, None)
            return value


def fold(text):
    """Text for searching: no accents, no case."""
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c)).casefold()


def same_folder(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


THUMB_VERSION = 1  # bump when facepack.thumbnail draws differently: the disk cache starts over


class FaceService:
    def __init__(self, game, cache_root=None):
        self.game = game
        self._template = None
        self._converted = _Lru(6)
        self._thumbs = _Lru(600)
        self._thumb_dir = os.path.join(cache_root, 'faces', 'thumbs') if cache_root else None
        self._packs = {}  # normalized folder -> (stamp, pack): read again only when the pack's folders change
        self._lock = threading.Lock()

    # ------------------------------------------------------------ pack
    def assets(self, folder):
        assets = facepack.assets_dir(folder)
        if not assets:
            raise FaceError('facepack_not_found', 'Pasta sem faces do FIFA 14 (procure a pasta que contém “screenassets”).')
        return assets

    def parts(self, folder):
        """The packs inside a folder the user set (facepack.find_parts: itself, data/sceneassets/, or several
        versions side by side), FaceError when none has faces: [{'folder' (the part's own folder: with the id, it
        identifies a face), 'root' (the folder set), 'name', 'faces', 'warnings'}]. Each face (facepack.list_faces)
        comes with what the manifest.json says about it (name, credits, credits_url). Each part is kept in memory
        and read again only when its folders or its manifest change."""
        found = facepack.find_parts(folder)
        if not found:
            raise FaceError('facepack_not_found', 'Pasta sem faces do FIFA 14 (procure a pasta que contém “screenassets”).')
        root = os.path.normpath(folder)
        return [self._part(root, assets, label) for assets, label in found]

    def _part(self, root, assets, label):
        key = os.path.normcase(os.path.normpath(assets))
        stamp = (root, label, _pack_stamp(assets, root))
        with self._lock:
            known = self._packs.get(key)
        if known and known[0] == stamp:
            return known[1]
        manifest, warnings = facepack.read_manifest(assets, root)
        name = os.path.basename(root) + (f' / {label}' if label else '')
        if warnings:
            log.warning('face pack %s: manifest.json %s', name, warnings)
        faces = [{**f, **manifest.get(f['id'], {})} for f in facepack.list_faces(assets)]
        part = {'folder': os.path.normpath(assets), 'root': root, 'label': label, 'name': name, 'faces': faces,
                'warnings': warnings}
        with self._lock:
            self._packs[key] = (stamp, part)
        return part

    def packs(self, folders):
        """[{'folder', 'root', 'index', 'name', 'count', 'warnings', 'error'}] of the parts of the folders, in their
        order (index = position of its folder in `folders`); a folder without faces is one entry with error = its
        FaceError code (and name = the folder name) instead of refusing the others."""
        out = []
        for index, folder in enumerate(folders):
            try:
                out += [{'folder': p['folder'], 'root': p['root'], 'index': index, 'name': p['name'],
                         'count': len(p['faces']), 'warnings': p['warnings'], 'error': None} for p in self.parts(folder)]
            except FaceError as e:
                root = os.path.normpath(folder)
                out.append({'folder': root, 'root': root, 'index': index, 'name': os.path.basename(root), 'count': 0,
                            'warnings': [], 'error': e.code})
        return out

    def page(self, folders, offset=0, limit=60, q='', pack=None):
        """One page of the faces of all the packs (in the order of the folders, then by part and id): {'total'
        (matching the filters), 'items', 'packs' (self.packs)}. q looks in the id, the name, the credits and the pack
        name (no accents, no case); pack = folder of one part only."""
        packs = self.packs(folders)
        query = fold(q.strip())
        matching = []
        for summary in packs:
            if summary['error'] or (pack and not same_folder(pack, summary['folder'])):
                continue
            p = self._part_of(summary['folder'])
            for face in p['faces']:
                if query and not any(query in fold(str(v)) for v in (face['id'], face.get('name'), face.get('credits'),
                                                                     p['name']) if v is not None):
                    continue
                matching.append({**face, 'folder': p['folder'], 'pack': p['name']})
        return {'total': len(matching), 'items': matching[offset:offset + limit], 'packs': packs}

    def _part_of(self, folder):
        """The part whose own folder is `folder` (as the gallery items give it): the one already read (it knows the
        folder the user set, for the manifest), else `folder` read as a pack of its own."""
        with self._lock:
            known = self._packs.get(os.path.normcase(os.path.normpath(folder)))
        if known:
            part = known[1]
            return self._part(part['root'], part['folder'], part['label'])
        assets = self.assets(folder)
        root = facepack.pack_root(assets)
        return self._part(os.path.normpath(root), assets, '')

    def face_info(self, folder, face_id):
        """(name of the part, what the manifest says about one face: {'name', 'credits', 'credits_url'}, keys only
        when known) of a face of the gallery (folder = the item's folder)."""
        part = self._part_of(folder)
        for face in part['faces']:
            if face['id'] == face_id:
                return part['name'], {k: face[k] for k in ('name', 'credits', 'credits_url') if face.get(k)}
        return part['name'], {}

    def thumbnail(self, key, files):
        try:
            return self._thumbs.get(key, lambda: self._thumb_on_disk(key, lambda: facepack.thumbnail(files)))
        except (ValueError, LookupError, ArithmeticError, TypeError, OSError, struct.error) as e:
            raise _unsupported(key, e) from e

    def _thumb_on_disk(self, key, make):
        """Gallery thumbnails are drawn from the 3D head (slow with thousands of faces): kept as PNG files in the
        cache folder, named after the face's files (their path, size and date)."""
        if not self._thumb_dir:
            return make()
        name = hashlib.sha1(repr((THUMB_VERSION, key)).encode()).hexdigest()
        path = os.path.join(self._thumb_dir, name[:2], f'{name}.png')
        try:
            with open(path, 'rb') as f:
                return f.read()
        except OSError:
            pass
        data = make()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f'{path}.{uuid.uuid4().hex}.tmp'  # requests run in parallel threads: write whole, then rename
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError as e:  # no cache: the thumbnail still goes out
            log.warning('face thumbnail not cached: %s', e)
        return data

    def _pack_files(self, assets, face_id):
        try:
            files = facepack.read_face(assets, face_id)
        except scanface.FaceFormatError as e:
            raise _unsupported((assets, face_id), e) from e
        if any(k not in files for k in scanface.REQUIRED):
            raise FaceError('face_not_found', f'Face {face_id} não encontrada no pack.', 404)
        return files

    def copy_to_project(self, folder, face_id, project_folder, player_uid):
        """Copies one face's pack files into the project (folder = the gallery item's folder)."""
        assets = self.assets(folder)
        scanface.write_files(scanface.project_face_dir(project_folder, player_uid), face_id,
                             self._pack_files(assets, face_id))

    # ------------------------------------------------------------ converted preview
    def source_files(self, folder=None, face_id=None, project_folder=None, player_uid=None):
        """(cache key, pack files) of a face in a pack (folder) or already in the project (player_uid)."""
        if player_uid:
            base = scanface.project_face_dir(project_folder, player_uid)
        else:
            base = self.assets(folder)
        try:
            files = scanface.read_files(base, face_id)
        except scanface.FaceFormatError as e:
            raise _unsupported((base, face_id), e) from e
        if any(k not in files for k in scanface.REQUIRED):
            raise FaceError('face_not_found', f'Face {face_id} não encontrada.', 404)
        return (base, face_id, _stamp(base, face_id)), files

    def converted(self, key, files, haircolorcode, paint=True, hair_mode='standard',
                  hair_thickness=scanface.HAIR_THICKNESS):
        """{kind: RX3b bytes} of the face converted like the build will (hair color painted on the scalp unless
        paint is False; hair_mode: scanface.HAIR_MODES; hair_thickness: its 'thick' step). A face that does not convert
        raises FaceError (kept in the cache: the 3D preview asks for 8 files of the same conversion at once)."""
        def make():
            with self._lock:
                if self._template is None:
                    self._template = scanface.template_files(self.game)
            try:
                out = scanface.convert(self._template, files, scanface.TEMPLATE, preview.hair_color(haircolorcode),
                                       paint=paint, hair_mode=hair_mode, hair_thickness=hair_thickness)
            except scanface.FaceFormatError as e:
                return _unsupported(key, e)
            return {kind: out[f.format(scanface.TEMPLATE)] for kind, f in scanface.FILES.items()
                    if f.format(scanface.TEMPLATE) in out}
        if 'thick' not in scanface.HAIR_MODES[hair_mode]:
            hair_thickness = scanface.HAIR_THICKNESS  # no effect: one cache entry
        result = self._converted.get((key, haircolorcode, paint, hair_mode, hair_thickness), make)
        if isinstance(result, FaceError):
            raise result
        return result


def _pack_stamp(assets, root):
    """Changes when a face is added to / removed from the pack (the dates of its folders) or its manifest changes
    (its own or the one of the folder set, root)."""
    paths = [os.path.join(assets, os.path.dirname(f)) for f in scanface.FILES.values()]
    paths += [os.path.join(facepack.pack_root(assets), facepack.PHOTOS), facepack.manifest_path(assets),
              os.path.join(root, facepack.MANIFEST)]
    out = []
    for path in dict.fromkeys(paths):
        try:
            st = os.stat(path)
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def _stamp(base, face_id):
    """Changes when any of the face's files changes (cache key)."""
    out = []
    for f in scanface.FILES.values():
        path = os.path.join(base, *f.format(face_id).split('/'))
        try:
            st = os.stat(path)
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)
