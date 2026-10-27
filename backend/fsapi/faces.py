"""Real faces (FIFA 14 packs) for the player's Visual tab: pick the pack folder, gallery, 3D preview, copy.

The pack stays where the user keeps it (read in place, never written); picking a face copies only that face's
files into the project (scanface.PROJECT_DIR/<player uid>/). The 3D preview shows the face already converted
(fsmod.scanface, ~3 s), so it is what the game will draw; conversions and thumbnails are cached in memory.
"""
import os
import threading
from collections import OrderedDict

from fsmod import facepack, preview, scanface


class FaceError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


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


class FaceService:
    def __init__(self, game):
        self.game = game
        self._template = None
        self._converted = _Lru(6)
        self._thumbs = _Lru(600)
        self._lock = threading.Lock()

    # ------------------------------------------------------------ pack
    def assets(self, folder):
        assets = facepack.assets_dir(folder)
        if not assets:
            raise FaceError('facepack_not_found', 'Pasta sem faces do FIFA 14 (procure a pasta que contém “screenassets”).')
        return assets

    def list(self, folder):
        assets = self.assets(folder)
        return {'folder': os.path.normpath(folder), 'name': facepack.pack_name(assets),
                'faces': facepack.list_faces(assets)}

    def thumbnail(self, key, files):
        return self._thumbs.get(key, lambda: facepack.thumbnail(files))

    def _pack_files(self, assets, face_id):
        files = facepack.read_face(assets, face_id)
        if any(k not in files for k in scanface.REQUIRED):
            raise FaceError('face_not_found', f'Face {face_id} não encontrada no pack.', 404)
        return files

    def copy_to_project(self, folder, face_id, project_folder, player_uid):
        """Copies one face's pack files into the project; returns the pack name."""
        assets = self.assets(folder)
        scanface.write_files(scanface.project_face_dir(project_folder, player_uid), face_id,
                             self._pack_files(assets, face_id))
        return facepack.pack_name(assets)

    # ------------------------------------------------------------ converted preview
    def source_files(self, folder=None, face_id=None, project_folder=None, player_uid=None):
        """(cache key, pack files) of a face in a pack (folder) or already in the project (player_uid)."""
        if player_uid:
            base = scanface.project_face_dir(project_folder, player_uid)
        else:
            base = self.assets(folder)
        files = scanface.read_files(base, face_id)
        if any(k not in files for k in scanface.REQUIRED):
            raise FaceError('face_not_found', f'Face {face_id} não encontrada.', 404)
        return (base, face_id, _stamp(base, face_id)), files

    def converted(self, key, files, haircolorcode, paint=True):
        """{kind: RX3b bytes} of the face converted like the build will (hair color painted on the scalp unless
        paint is False)."""
        def make():
            with self._lock:
                if self._template is None:
                    self._template = scanface.template_files(self.game)
            out = scanface.convert(self._template, files, scanface.TEMPLATE, preview.hair_color(haircolorcode),
                                  paint=paint)
            return {kind: out[f.format(scanface.TEMPLATE)] for kind, f in scanface.FILES.items()
                    if f.format(scanface.TEMPLATE) in out}
        return self._converted.get((key, haircolorcode, paint), make)


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
