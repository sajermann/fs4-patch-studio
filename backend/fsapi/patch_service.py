"""Building the patch folder and installing it into the game.

patch/ mirrors the game root of ReStreet 2.x: Game/data8.big/.bh + every game file the app can change, whole
(Game/data1.big, Game/data/loc/locale.big, ...; the original when unchanged), see fsmod.builder.write_patch. patch/patch.json records which
project content it was built from, so the UI can say "changes not built yet".
Installing copies the patch over the game (game closed) and deletes the save, so the game creates a new one from
the modded database; uninstalling puts the original files back.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

from fsmod import builder
from fsmod.game import GAME_DATA

from . import game_setup

PATCH_INFO = 'patch.json'
GAME_MANIFEST = '.fsmod_manifest.json'
GAME_PROCESS = 'fifastreet.exe'
DISK_MARGIN = 200 * 1024 * 1024  # free space kept on the game's disk after an install


class InstallError(Exception):
    pass


def build_patch(project, store, game, patch_dir, log=None, progress=None):
    """Builds the patch from the saved project. Ids given by the build are written back.
    progress(step, done, total): see builder.BUILD_STEPS."""
    result = builder.build(project, game, store.folder, log=log, progress=progress)
    if result.assigned_league_ids or result.assigned_team_ids or result.assigned_player_ids:
        for league in project.leagues:
            if league.uid in result.assigned_league_ids:
                league.league_id = result.assigned_league_ids[league.uid]
        for team in project.teams:
            if team.uid in result.assigned_team_ids:
                team.team_id = result.assigned_team_ids[team.uid]
        for player in project.players:
            if player.uid in result.assigned_player_ids:
                player.player_id = result.assigned_player_ids[player.uid]
        store.save(project)
    builder.write_patch(result, game, patch_dir, progress=progress)
    info = {'built_at': datetime.datetime.now().isoformat(timespec='seconds'),
            'project_hash': store.content_hash(),
            'files': patch_files(patch_dir)}
    with open(os.path.join(patch_dir, PATCH_INFO), 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2)
    return result


def patch_files(patch_dir):
    """['Game/data8.big', 'Game/data/loc/locale.big', ...]: what the user copies over the game root."""
    folder = os.path.join(patch_dir, GAME_DATA)
    return sorted(os.path.relpath(os.path.join(root, n), patch_dir).replace(os.sep, '/')
                  for root, _, names in os.walk(folder) for n in names)


def patch_status(store, patch_dir):
    path = os.path.join(patch_dir, PATCH_INFO)
    if not os.path.exists(path):
        return {'built': False, 'up_to_date': False}
    with open(path, encoding='utf-8') as f:
        info = json.load(f)
    return {'built': True, 'built_at': info['built_at'], 'files': info['files'],
            'up_to_date': info['project_hash'] == store.content_hash()}


def game_running():
    try:
        out = subprocess.run(['tasklist'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return GAME_PROCESS in out.lower()


def _read_manifest(game_data):
    """{rel: [size, mtime_ns, sha1]} of what the last install wrote (None: nothing installed by the app). An old
    manifest (a plain list of paths) has no fingerprints."""
    try:
        with open(os.path.join(game_data, GAME_MANIFEST), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return {rel: None for rel in data} if isinstance(data, list) else data.get('files', {})


def _write_manifest(game_data, files):
    with open(os.path.join(game_data, GAME_MANIFEST), 'w', encoding='utf-8') as f:
        json.dump({'version': 2, 'files': files}, f, indent=2)


def _copy_atomic(src, dst):
    """Copies src to dst through a temporary file renamed at the end (an interrupted copy never leaves half a file
    under the real name); returns the SHA-1 of what was copied."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.fsmod_tmp'
    h = hashlib.sha1()
    try:
        with open(src, 'rb') as fin, open(tmp, 'wb') as fout:
            for block in iter(lambda: fin.read(1 << 24), b''):
                h.update(block)
                fout.write(block)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return h.hexdigest()


def _fingerprint(path, sha1):
    st = os.stat(path)
    return [st.st_size, st.st_mtime_ns, sha1]


def _put_back(game_data, original_dir, rel):
    """The game file as it was before the app: the original (copied back) or nothing (an added file is removed).
    Returns 'restored' / 'removed' / None."""
    target = os.path.join(game_data, rel)
    original = os.path.join(original_dir, GAME_DATA, rel)
    if os.path.isfile(original):
        _copy_atomic(original, target)
        return 'restored'
    if os.path.exists(target):
        os.remove(target)
        return 'removed'
    return None


def _remove_empty_dirs(game_data):
    for root, dirs, _ in os.walk(game_data, topdown=False):
        for d in dirs:
            path = os.path.join(root, d)
            if not os.listdir(path):
                os.rmdir(path)


def _check_target(game_dir, save_dir, check_running):
    game_data = os.path.join(game_dir, GAME_DATA) if game_dir else None
    if not game_data or not os.path.isfile(os.path.join(game_data, 'data0.big')):
        raise InstallError('game_dir_invalid')
    if check_running and game_running():
        raise InstallError('game_running')
    if not game_setup.is_save_dir(save_dir):
        raise InstallError('save_dir_invalid')
    return game_data


def install(patch_dir, game_dir, backups_dir, original_dir, save_dir, check_running=True):
    """Copies patch/Game over <game_dir>/Game and deletes the save (the game reads leagues/teams/players from it,
    so every mod needs a new one; decision of the user 23/10: no copy kept). Returns a report dict.

    Files installed before and no longer in the patch go back to the original (original_dir) or are removed.
    Every file is copied under a temporary name and renamed when complete; if anything fails, what this install
    already wrote is put back. GAME_MANIFEST lists what was written (size, mtime, SHA-1) for uninstall and for
    noticing later changes. A data8 the app did not install (no manifest) is backed up first.
    """
    game_data = _check_target(game_dir, save_dir, check_running)
    files = patch_files(patch_dir)
    if not os.path.exists(os.path.join(patch_dir, PATCH_INFO)) or not files:
        raise InstallError('patch_missing')
    new = [rel.split('/', 1)[1] for rel in files]
    need = sum(os.path.getsize(os.path.join(patch_dir, GAME_DATA, rel)) for rel in new)
    if shutil.disk_usage(game_data).free < need + DISK_MARGIN:  # the temporary copies need room before the renames
        raise InstallError('disk_full')

    previous = _read_manifest(game_data)
    backup = None
    if previous is None and any(os.path.exists(os.path.join(game_data, n)) for n in ('data8.big', 'data8.bh')):
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = os.path.join(backups_dir, f'data8_before_app_{stamp}')
        os.makedirs(backup, exist_ok=True)
        for name in ('data8.big', 'data8.bh'):
            if os.path.exists(os.path.join(game_data, name)):
                shutil.copy2(os.path.join(game_data, name), backup)

    restored, removed, written = [], [], {}
    try:
        for rel in previous or {}:
            if rel not in new:
                done = _put_back(game_data, original_dir, rel)
                if done:
                    (restored if done == 'restored' else removed).append(rel)
        for rel in new:
            target = os.path.join(game_data, rel)
            written[rel] = _fingerprint(target, _copy_atomic(os.path.join(patch_dir, GAME_DATA, rel), target))
    except BaseException:
        for rel in written:  # back to the originals (an earlier patch of the app is not brought back)
            _put_back(game_data, original_dir, rel)
        _remove_empty_dirs(game_data)
        if os.path.exists(os.path.join(game_data, GAME_MANIFEST)):
            os.remove(os.path.join(game_data, GAME_MANIFEST))
        raise
    _write_manifest(game_data, written)
    return {'backup': backup, 'installed': files, 'restored': restored, 'removed': removed,
            'save_removed': game_setup.delete_save(save_dir)}


def uninstall(game_dir, original_dir, save_dir, check_running=True):
    """Puts the game back as the originals: every file the app installed is copied back from original_dir or, when
    the game has no such file (data8, loose crests/kits/photos/flags), removed. Deletes the save too."""
    game_data = _check_target(game_dir, save_dir, check_running)
    previous = _read_manifest(game_data)
    if previous is None:
        raise InstallError('not_installed')
    restored, removed = [], []
    for rel in previous:
        done = _put_back(game_data, original_dir, rel)
        if done:
            (restored if done == 'restored' else removed).append(rel)
    os.remove(os.path.join(game_data, GAME_MANIFEST))
    _remove_empty_dirs(game_data)
    return {'restored': restored, 'removed': removed, 'save_removed': game_setup.delete_save(save_dir)}


def installed_state(game_dir):
    """{'installed': the app's patch is in the game, 'changed': files changed outside the app since}. Cheap: a file
    is hashed only when its size/mtime differ from the manifest."""
    game_data = os.path.join(game_dir, GAME_DATA) if game_dir else None
    manifest = _read_manifest(game_data) if game_data and os.path.isdir(game_data) else None
    if manifest is None:
        return {'installed': False, 'changed': []}
    changed, refreshed = [], False
    for rel, fp in manifest.items():
        path = os.path.join(game_data, rel)
        if fp is None:
            continue
        if not os.path.isfile(path):
            changed.append(rel)
            continue
        st = os.stat(path)
        if [st.st_size, st.st_mtime_ns] == fp[:2]:
            continue
        if st.st_size == fp[0] and game_setup.sha1_file(path) == fp[2]:
            manifest[rel], refreshed = [st.st_size, st.st_mtime_ns, fp[2]], True  # touched, same content
        else:
            changed.append(rel)
    if refreshed:
        _write_manifest(game_data, manifest)
    return {'installed': True, 'changed': sorted(changed)}


def export_patch(patch_dir, zip_path):
    """Zip of the patch's Game folder (stored, not compressed: the archives barely shrink and it is much faster),
    to be copied over the game by hand."""
    files = patch_files(patch_dir)
    if not os.path.exists(os.path.join(patch_dir, PATCH_INFO)) or not files:
        raise InstallError('patch_missing')
    tmp = zip_path + '.fsmod_tmp'
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
            for rel in files:
                z.write(os.path.join(patch_dir, *rel.split('/')), rel)
        os.replace(tmp, zip_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {'path': zip_path, 'files': len(files)}
