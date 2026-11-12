"""Cache of the slow files of a build (real faces, real kits) between builds.

Each entry is the {internal name: bytes} a converter made, stored under a key: the SHA-256 of everything that goes into
it (the input files' bytes, the options, the target ids) plus CODE_VERSION, a hash of the fsmod sources, so a new
version of the app never reuses files made by an older converter. The original game files the converters read are in
the key through the caller's game fingerprint (sizes and dates of the originals).

The folder can be deleted at any time: the next build makes everything again. prune() deletes what the last build
did not use, so the folder never grows past one build's files. Entries are zip files (stored, no compression: the
files are already compressed), written to a temporary name first.
"""
import hashlib
import json
import os
import sys
import uuid
import zipfile

_FSMOD_DIR = os.path.dirname(os.path.abspath(__file__))


def _code_version():
    """Hash of the fsmod sources; in the packaged app (no .py files) the executable's size and date, which change
    with every release."""
    h = hashlib.sha256()
    try:
        names = sorted(n for n in os.listdir(_FSMOD_DIR) if n.endswith('.py'))
    except OSError:
        names = []
    for name in names:
        with open(os.path.join(_FSMOD_DIR, name), 'rb') as f:
            h.update(name.encode() + b'\0' + f.read())
    if not names:
        st = os.stat(sys.executable)
        h.update(f'frozen:{st.st_size}:{int(st.st_mtime)}'.encode())
    return h.hexdigest()


CODE_VERSION = _code_version()


def game_fingerprint(game):
    """Sizes and modification times of the original files the converters read (fsmod.game.GameSources)."""
    parts = []
    for name in sorted(game.fingerprint_files()):
        try:
            st = os.stat(name)
            parts.append(f'{os.path.basename(name)}:{st.st_size}:{int(st.st_mtime)}')
        except OSError:
            parts.append(f'{os.path.basename(name)}:missing')
    return '|'.join(parts)


def key(kind, *parts):
    """Cache key of an entry: kind (e.g. 'face') + its inputs (bytes, str, numbers, JSON-able values)."""
    h = hashlib.sha256(f'{kind}\0{CODE_VERSION}\0'.encode())
    for p in parts:
        if isinstance(p, (bytes, bytearray)):
            h.update(b'b' + len(p).to_bytes(8, 'little') + bytes(p))
        else:
            data = json.dumps(p, sort_keys=True, default=str).encode()
            h.update(b'j' + len(data).to_bytes(8, 'little') + data)
    return h.hexdigest()


def file_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


class BuildCache:
    """folder: where the entries live (created when needed). None = no cache (every get misses, put does nothing)."""

    def __init__(self, folder):
        self.folder = folder
        self.used = set()
        self.hits = self.misses = 0
        self.reused_files = 0  # files (internal names) the hits gave: each one becomes a file of the patch

    def _path(self, k):
        return os.path.join(self.folder, k[:2], k + '.zip')

    def get(self, k):
        """{name: bytes} stored under k, or None."""
        if not self.folder:
            self.misses += 1
            return None
        self.used.add(k)
        try:
            with zipfile.ZipFile(self._path(k)) as z:
                files = {info.filename: z.read(info) for info in z.infolist()}
        except (OSError, zipfile.BadZipFile, KeyError):
            self.misses += 1
            return None
        self.hits += 1
        self.reused_files += len(files)
        return files

    def put(self, k, files):
        if not self.folder:
            return
        self.used.add(k)
        path = self._path(k)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f'{path}.{uuid.uuid4().hex[:8]}.tmp'
            with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:
                for name, data in files.items():
                    z.writestr(name, data)
            os.replace(tmp, path)
        except OSError:  # a cache that cannot be written only makes the next build slower
            pass

    def prune(self):
        """Deletes the entries this build did not use (and leftover temporary files)."""
        if not self.folder or not os.path.isdir(self.folder):
            return 0
        removed = 0
        for root, _, names in os.walk(self.folder):
            for name in names:
                if name.endswith('.tmp') or (name.endswith('.zip') and name[:-4] not in self.used):
                    try:
                        os.remove(os.path.join(root, name))
                        removed += 1
                    except OSError:
                        pass
        return removed
