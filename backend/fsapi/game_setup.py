"""The user's game folder: which ReStreet it is, whether its files are the official ones, importing them as the
app's originals, the save folder and deleting the save.

The app builds every patch from its own copy of 12 game files (original_files/). They are only imported when
they match OFFICIAL_FILES (size + SHA-1), so a game that already has a mod (or an earlier patch copied by hand)
never becomes the base of a patch. A fingerprint (size + mtime) of each file kept next to them makes the check done
on every start cheap: a file is hashed again only when its fingerprint changed (kept next to the config, never
inside original_files/).
"""
import ctypes
import hashlib
import json
import os
import shutil
import threading
import uuid

# the files the app reads from the game (= fsmod.game sources), the same in ReStreet 2.0.4, 2.0.8 and 2.1.3
OFFICIAL_FILES = {
    'Game/data0.bh': (5356, '2a2201b565673dee9feeb3a0b84c4abb65f24ca4'),
    'Game/data0.big': (7165026, 'e5a8e869ad4c55de392c214989036ef095001919'),
    'Game/data1.bh': (384136, '5cc65337060e8d9b10748addb63eb083d5d96750'),
    'Game/data1.big': (546215104, '283d2d9fc5bf2702d776699f5231f25fa2b06e29'),
    'Game/data3.bh': (314116, '4cad0d0382217f156fe714820382da14297f1ec9'),
    'Game/data3.big': (1162629608, '60d8d2ba9f54527e8111bd1f526b3656588a5be3'),
    'Game/data7.bh': (75676, 'fcb0d22b8e9b47b90f115fe6668038acfc322cdf'),
    'Game/data7.big': (351991936, '8b601b6e6361be1b7109fad54e583413019b498b'),
    'Game/data/loc/locale.big': (5264336, '714a0dbcd68ccecf5013343d2cbcc05057fe4de8'),
    'Game/data/loc/locale_ptbr.big': (5236880, '044c0d76f0bd2967cede5cb66915c1b86532d48a'),
    'Game/data/ui/imgAssets/heads/2dheads.bh': (30296, 'cbd01cb10d6d881e7e85a1cf2ea59469f080baac'),
    'Game/data/ui/imgAssets/heads/2dheads.big': (11214872, '7623c487c680adb924d464a30b0f3903c648bf0d'),
}
# files a clean ReStreet does not have: a mod's database (what every patch adds, ours too)
MOD_FILES = ('Game/data8.big', 'Game/data8.bh')
TESTED_VERSIONS = ('2.0.4', '2.0.8', '2.1.3')  # ReStreet versions the app was validated with in game
TERMS_VERSION = 1  # bump when the text of the first-run screen changes: everyone accepts it again
TITLE_ID = '4541097B'  # FIFA Street: the save is <Documents>/fifastreet/<profile>/4541097B
SAVE_SUBDIRS = ('00000001', os.path.join('Headers', '00000001'))
CHUNK = 1 << 24


class SetupError(Exception):
    pass


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def restreet_version(game_dir):
    """'2.0.8' from the ReStreet installer's online-patch.json ("PatchVersion": "2.0.8-online"); None if unknown."""
    try:
        with open(os.path.join(game_dir, 'online-patch.json'), encoding='utf-8-sig') as f:
            version = json.load(f).get('PatchVersion') or ''
    except (OSError, ValueError, AttributeError):
        return None
    return version.split('-')[0] or None


def is_game_root(game_dir):
    """The ReStreet root: the folder that holds Game (with data0.big) and Binaries."""
    return bool(game_dir) and os.path.isfile(os.path.join(game_dir, 'Game', 'data0.big'))


def check_files(folder):
    """{rel: 'ok' | 'missing' | 'different'} of the official files under folder (size first, then SHA-1); check_game
    also marks 'added' a mod's database (MOD_FILES)."""
    out = {}
    for rel, (size, sha1) in OFFICIAL_FILES.items():
        path = os.path.join(folder, *rel.split('/'))
        if not os.path.isfile(path):
            out[rel] = 'missing'
        elif os.path.getsize(path) != size or sha1_file(path) != sha1:
            out[rel] = 'different'
        else:
            out[rel] = 'ok'
    return out


APP_MANIFEST = os.path.join('Game', '.fsmod_manifest.json')  # = patch_service.GAME_MANIFEST, written by installs


def app_patch_installed(game_dir):
    """The game has a patch installed by this app (its manifest): the app knows every file it wrote and can undo it."""
    return bool(game_dir) and os.path.isfile(os.path.join(game_dir, APP_MANIFEST))


def check_game(game_dir):
    """What the first-run screen shows about a folder the user picked. `accepted`: the 12 files are the official
    ones, or what differs is a patch of this app. A game with any other mod (or a patch copied by hand) is refused:
    the app would not know what that mod added (data8, loose crests/kits...) and could never undo it."""
    if not is_game_root(game_dir):
        return {'valid': False, 'version': None, 'tested': False, 'files': {}, 'official': False,
                'app_patch': False, 'accepted': False}
    version = restreet_version(game_dir)
    files = check_files(game_dir)
    app_patch = app_patch_installed(game_dir)
    if not app_patch:  # a patch only adds files when it changes no text: data8 gives it away
        files.update({rel: 'added' for rel in MOD_FILES if os.path.isfile(os.path.join(game_dir, *rel.split('/')))})
    official = all(s == 'ok' for s in files.values())
    return {'valid': True, 'version': version, 'tested': version in TESTED_VERSIONS, 'files': files,
            'official': official, 'app_patch': app_patch, 'accepted': official or app_patch}


class Originals:
    """The app's copy of the official files (original_files/) and its fingerprints."""

    def __init__(self, folder, prints_path):
        self.folder, self.prints_path = folder, prints_path
        self._lock = threading.Lock()

    def _path(self, rel):
        return os.path.join(self.folder, *rel.split('/'))

    def _load(self):
        try:
            with open(self.prints_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self, prints):
        os.makedirs(os.path.dirname(self.prints_path) or '.', exist_ok=True)
        with open(self.prints_path, 'w', encoding='utf-8') as f:
            json.dump(prints, f, indent=2)

    def state(self):
        """{'complete': all present, 'verified': all official, 'missing': [...], 'modified': [...]}. Cheap: only a
        file whose size/mtime changed since the last check is hashed again."""
        with self._lock:
            prints, changed = self._load(), False
            missing, modified = [], []
            for rel, (size, sha1) in OFFICIAL_FILES.items():
                path = self._path(rel)
                if not os.path.isfile(path):
                    missing.append(rel)
                    continue
                st = os.stat(path)
                stamp = [st.st_size, st.st_mtime_ns]
                if prints.get(rel) == stamp:
                    continue
                if st.st_size == size and sha1_file(path) == sha1:
                    prints[rel], changed = stamp, True
                else:
                    prints.pop(rel, None)
                    modified.append(rel)
            if changed:
                self._save(prints)
            return {'complete': not missing, 'verified': not missing and not modified, 'missing': missing,
                    'modified': modified}

    def import_from(self, game_dir):
        """Copies the official files of game_dir (checked first) over the app's copy; files already official stay.
        Each file goes to a temporary name and is renamed only when complete."""
        found = check_files(game_dir)
        bad = sorted(rel for rel, s in found.items() if s != 'ok')
        if bad:
            raise SetupError(f'files not official: {", ".join(bad)}')
        mine = self.state()
        todo = set(mine['missing']) | set(mine['modified'])
        with self._lock:
            prints = self._load()
            for rel in OFFICIAL_FILES:
                if rel not in todo:
                    continue
                dst = self._path(rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                tmp = f'{dst}.{uuid.uuid4().hex}.tmp'
                try:
                    shutil.copyfile(os.path.join(game_dir, *rel.split('/')), tmp)
                    os.replace(tmp, dst)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                st = os.stat(dst)
                prints[rel] = [st.st_size, st.st_mtime_ns]
            self._save(prints)
        return sorted(todo)


def documents_dir():
    """The user's Documents folder as Windows says (it may be moved off C:, e.g. E:\\Backup\\...\\Documents)."""
    if os.name == 'nt':
        class GUID(ctypes.Structure):
            _fields_ = [('d1', ctypes.c_ulong), ('d2', ctypes.c_ushort), ('d3', ctypes.c_ushort),
                        ('d4', ctypes.c_ubyte * 8)]
        documents = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69,
                                                                           0xC7))
        path = ctypes.c_wchar_p()
        try:
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(documents), 0, None, ctypes.byref(path)) == 0:
                try:
                    return path.value
                finally:
                    ctypes.windll.ole32.CoTaskMemFree(path)
        except (AttributeError, OSError):
            pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def guess_save_dir():
    """<Documents>/fifastreet/<profile>/4541097B of the profile with the most recent save; None when not found."""
    root = os.path.join(documents_dir(), 'fifastreet')
    found = []
    if os.path.isdir(root):
        for profile in os.listdir(root):
            folder = os.path.join(root, profile, TITLE_ID)
            if os.path.isdir(folder):
                found.append((os.path.getmtime(folder), folder))
    return max(found)[1] if found else None


def is_save_dir(save_dir):
    """Only a FIFA Street profile folder (…/4541097B) is ever touched: a wrong path can't delete anything else."""
    return bool(save_dir) and os.path.basename(os.path.normpath(save_dir)).upper() == TITLE_ID and \
        os.path.isdir(save_dir)


def delete_save(save_dir):
    """Deletes the save (00000001 and Headers/00000001 of the profile); the game creates a new one from the
    database. Returns how many files went. The app keeps no copy (decision of the user, 23/10)."""
    if not is_save_dir(save_dir):
        raise SetupError('save_dir_invalid')
    removed = 0
    for sub in SAVE_SUBDIRS:
        folder = os.path.join(save_dir, sub)
        if os.path.isdir(folder):
            removed += sum(len(files) for _, _, files in os.walk(folder))
            shutil.rmtree(folder)
    return removed
