"""Cache of the slow files of a build (real faces, real kits) between builds.

Each entry is the {internal name: bytes} a converter made, stored under a key: the SHA-256 of everything that goes into
it (the input files' bytes, the options, the target ids) plus the version of the converter's code (code_version: a
hash of the fsmod modules it is made of, found through their imports), so files made by an older converter are never
reused, while a change elsewhere in the app keeps the cache. The original game files the converters read are in the
key through the caller's game fingerprint (sizes and dates of the originals).

Entries are written as soon as each conversion ends (not when the build gets to it in its order), so a build that
fails or is stopped keeps everything it had already converted: the next one starts from there.

The folder can be deleted at any time: the next build makes everything again. prune() deletes what the last
(complete) build did not use, so the folder never grows past one build's files. Entries are zip files (stored, no
compression: the files are already compressed), written to a temporary name first.
"""
import ast
import functools
import hashlib
import inspect
import json
import os
import sys
import threading
import uuid
import zipfile

_FSMOD_DIR = os.path.dirname(os.path.abspath(__file__))


def _source(module):
    try:
        with open(os.path.join(_FSMOD_DIR, module + '.py'), 'rb') as f:
            return f.read()
    except OSError:
        return None


def fsmod_imports(source):
    """Names of the fsmod modules a source imports (from . import x, from .x import y, import fsmod.x...)."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            parts = (node.module or '').split('.')
            if node.level == 1:
                names.update([parts[0]] if node.module else [a.name for a in node.names])
            elif node.level == 0 and parts[0] == 'fsmod':
                names.update([parts[1]] if len(parts) > 1 else [a.name for a in node.names])
        elif isinstance(node, ast.Import):
            names.update(a.name.split('.')[1] for a in node.names if a.name.startswith('fsmod.'))
    return names


@functools.lru_cache(maxsize=None)
def code_version(*modules):
    """Hash of the given fsmod modules and of every fsmod module they import (directly or not), plus the tools in
    fsmod/bin; in the packaged app (no .py files) the executable's size and date, which change with every release."""
    seen, todo = set(), list(modules)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        source = _source(name)
        if source is not None:
            todo.extend(fsmod_imports(source))
    h = hashlib.sha256()
    found = [n for n in sorted(seen) if _source(n) is not None]
    for name in found:
        h.update(name.encode() + b'\0' + _source(name))
    bin_dir = os.path.join(_FSMOD_DIR, 'bin')
    for name in sorted(os.listdir(bin_dir)) if os.path.isdir(bin_dir) else []:
        h.update(f'bin:{name}:{os.path.getsize(os.path.join(bin_dir, name))}'.encode())
    if not found:
        st = os.stat(sys.executable)
        h.update(f'frozen:{st.st_size}:{int(st.st_mtime)}'.encode())
    return h.hexdigest()


def function_source(fn):
    """Source of a function, to be part of a key (the code that prepares a conversion's inputs); '' when there is
    none (packaged app, where code_version follows the executable)."""
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ''


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


def key(kind, version, *parts):
    """Cache key of an entry: kind (e.g. 'face'), the version of its converter's code (code_version) and its inputs
    (bytes, str, numbers, JSON-able values)."""
    h = hashlib.sha256(f'{kind}\0{version}\0'.encode())
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
    """folder: where the entries live (created when needed). None = no cache (every get misses, put does nothing).
    Safe to use from several threads (entries are written by the threads that see a conversion end)."""

    def __init__(self, folder):
        self.folder = folder
        self._lock = threading.Lock()
        self.used = set()
        self.hits = self.misses = 0
        self.reused_files = 0  # files (internal names) the hits gave: each one becomes a file of the patch

    def _path(self, k):
        return os.path.join(self.folder, k[:2], k + '.zip')

    def _count(self, hit, files=0):
        with self._lock:
            if hit:
                self.hits += 1
                self.reused_files += files
            else:
                self.misses += 1

    def get(self, k):
        """{name: bytes} stored under k, or None."""
        if not self.folder:
            self._count(False)
            return None
        with self._lock:
            self.used.add(k)
        try:
            with zipfile.ZipFile(self._path(k)) as z:
                files = {info.filename: z.read(info) for info in z.infolist()}
        except (OSError, zipfile.BadZipFile, KeyError):
            self._count(False)
            return None
        self._count(True, len(files))
        return files

    def put(self, k, files):
        if not self.folder:
            return
        with self._lock:
            self.used.add(k)
        path = self._path(k)
        if os.path.isfile(path):  # same key = same files (written as the worker ended; the build puts them again)
            return
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
        """Deletes the entries this build did not use (and leftover temporary files). Only after a complete build:
        a failed or stopped one keeps everything for the next."""
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
