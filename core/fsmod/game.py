"""Read-only access to the original game files the builder needs.

The app never reads the game installation directly: the user copies these files from the game's
Game folder (ReStreet 2.x layout) into app/backend/original_files/Game (same relative paths), see
REQUIRED_FILES. The database and its meta XML are extracted from data0.big.
"""
import os
import re
from functools import cached_property

from . import big, chunk, t3db

LOCALE_FILE = os.path.join('data', 'loc', 'locale.big')
LOCALE_PTBR_FILE = os.path.join('data', 'loc', 'locale_ptbr.big')  # read instead of locale.big in pt-BR (ReStreet 2.x)
LOCALE_FILES = (LOCALE_FILE, LOCALE_PTBR_FILE)
PHOTOS_FILE = os.path.join('data', 'ui', 'imgAssets', 'heads', '2dheads.big')  # player photos (p<playerid>.dds)
PHOTOS_INDEX = PHOTOS_FILE[:-4] + '.bh'
LOCALE_ENTRY = 'data/loc/eng_us.db'
# every language of a locale file (same keys; ReStreet's pt-BR file has the Portuguese texts in eng_us)
LOCALE_ENTRIES = tuple(f'data/loc/{lang}.db' for lang in ('eng_us', 'fre_fr', 'ger_de', 'ita_it', 'spa_es'))
DB_ENTRY = 'data/db/fifa_street_db.db'
META_ENTRY = 'data/db/fifa_street_db-meta.xml'
# data0: database; data1: menu crests and kit thumbnails; data3: kits (verified for all 379 team slots) and 3D meshes;
# data7: street clothes textures (3D preview, street kit options) and the far hair of scanned faces (hairlod)
ARCHIVES = (0, 1, 3, 7)
PATCHED_ARCHIVES = (1, 3, 7)
GAME_DATA = 'Game'  # game data folder (mounted as d:\); ReStreet 1.x called it GameData
# archives the builder may rewrite, by short name -> path inside GAME_DATA
PATCH_TARGETS = {f'data{k}.big': f'data{k}.big' for k in PATCHED_ARCHIVES}
PATCH_TARGETS.update({os.path.basename(f): f for f in (*LOCALE_FILES, PHOTOS_FILE)})
REQUIRED_FILES = ([os.path.join(GAME_DATA, f'data{k}.{ext}') for k in ARCHIVES for ext in ('big', 'bh')] +
                  [os.path.join(GAME_DATA, f) for f in (*LOCALE_FILES, PHOTOS_FILE, PHOTOS_INDEX)])


class MissingOriginalFiles(FileNotFoundError):
    def __init__(self, folder, missing):
        super().__init__(f'missing original game files in {folder}: {", ".join(missing)}')
        self.folder = folder
        self.missing = missing


class GameSources:
    def __init__(self, folder):
        self.folder = folder  # mirrors the game root: holds a Game folder

    def missing_files(self):
        return [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(self.folder, f))]

    def ensure_complete(self):
        missing = self.missing_files()
        if missing:
            raise MissingOriginalFiles(self.folder, missing)

    def _path(self, name):
        return os.path.join(self.folder, GAME_DATA, name)

    def target_path(self, short_name):
        """Original archive by short name (e.g. 'data1.big', 'locale_ptbr.big')."""
        return self._path(PATCH_TARGETS[short_name])

    def index_path(self, short_name):
        """Original .bh index of an archive, or None when the game has none (locale files)."""
        path = self.target_path(short_name)[:-4] + '.bh'
        return path if os.path.isfile(path) else None

    @cached_property
    def _data0_toc(self):
        return {name: (off, size) for name, off, size in big.read_toc_file(self._path('data0.big'))}

    def _data0_entry(self, name):
        off, size = self._data0_toc[name]
        with open(self._path('data0.big'), 'rb') as f:
            f.seek(off)
            return chunk.decode(f.read(size))

    @cached_property
    def _original_db(self):
        return self._data0_entry(DB_ENTRY)

    def original_db(self) -> bytes:
        return self._original_db

    @cached_property
    def meta(self):
        return t3db.parse_meta(self._data0_entry(META_ENTRY).decode('utf-8'))

    @cached_property
    def index(self):
        """{djb2(name): (archive number, offset, size)} over the original dataN.bh files."""
        idx = {}
        for k in ARCHIVES:
            with open(self._path(f'data{k}.bh'), 'rb') as f:
                entries = big.read_bh_entries(f.read())
            for off, size, _, h in entries:
                idx.setdefault(h, (k, off, size))
        return idx

    def locate(self, name):
        """(archive number, offset, size) of an internal file, or None."""
        return self.index.get(big.djb2(name.encode()))

    def read_entry(self, name):
        """(archive number, offset, raw bytes) of an internal file, or None."""
        loc = self.locate(name)
        if not loc:
            return None
        k, off, size = loc
        with open(self._path(f'data{k}.big'), 'rb') as f:
            f.seek(off)
            return k, off, f.read(size)

    @cached_property
    def db_bh_unknown(self):
        """Unknown .bh field of the data0 entries (copied into the patch .bh)."""
        names = list(self._data0_toc)
        with open(self._path('data0.bh'), 'rb') as f:
            return big.bh_unknown_by_name(f.read(), names)

    @cached_property
    def photo_index(self):
        """{playerid: (offset, size)} of the player photos in 2dheads.big."""
        out = {}
        for name, off, size in big.read_toc_file(self._path(PHOTOS_FILE)):
            m = re.fullmatch(r'data/ui/imgassets/heads/p(\d+)\.dds', name)
            if m:
                out[int(m.group(1))] = (off, size)
        return out

    def read_photo(self, playerid):
        """(offset, raw chunkzip bytes) of a player's photo."""
        off, size = self.photo_index[playerid]
        with open(self._path(PHOTOS_FILE), 'rb') as f:
            f.seek(off)
            return off, f.read(size)

    def locale(self, file=LOCALE_FILE, entry=LOCALE_ENTRY):
        """(offset inside the locale file, original database bytes). file: one of LOCALE_FILES; entry: one of
        LOCALE_ENTRIES (default English)."""
        for name, off, size in big.read_toc_file(self._path(file)):
            if name == entry:
                with open(self._path(file), 'rb') as f:
                    f.seek(off)
                    return off, f.read(size)
        raise FileNotFoundError(f'{entry} not found in {file}')


def default_original_files():
    """app/backend/original_files (overridable with FSMOD_ORIGINAL_FILES)."""
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.environ.get('FSMOD_ORIGINAL_FILES', os.path.join(app_dir, 'backend', 'original_files'))


def default_patch_dir():
    """app/backend/patch (overridable with FSMOD_PATCH_DIR)."""
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.environ.get('FSMOD_PATCH_DIR', os.path.join(app_dir, 'backend', 'patch'))


def default_sources():
    return GameSources(default_original_files())
