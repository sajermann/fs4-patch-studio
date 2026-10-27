import os
import shutil
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['FSMOD_NO_DEFAULT_APP'] = '1'
sys.path.insert(0, BACKEND)

from fsapi import settings  # noqa: E402
from fsapi.main import AppState, create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURE = os.path.join(settings.CORE_DIR, 'tests', 'fixtures', 'palmeiras')


@pytest.fixture(scope='session')
def original_files():
    from fsmod.game import GameSources, default_original_files
    game = GameSources(default_original_files())
    if game.missing_files():
        pytest.skip('original game files not available')
    return game.folder


@pytest.fixture
def env(tmp_path, original_files):
    """App wired to temporary project/patch/config folders and a fake game folder."""
    project_dir, patch_dir = tmp_path / 'project', tmp_path / 'patch'
    game_dir, save_dir = tmp_path / 'game', tmp_path / 'save' / 'fifastreet' / 'PROFILE' / '4541097B'
    make_fake_game(game_dir)
    make_fake_save(save_dir)
    config_path = tmp_path / 'config.json'
    settings.save_config(settings.Config(game_dir=str(game_dir), save_dir=str(save_dir),
                                         project_dir=str(project_dir), backups_dir=str(tmp_path / 'backups'),
                                         terms_version=1),
                         str(config_path))
    state = AppState(original_files, str(patch_dir), str(config_path))
    return {'client': TestClient(create_app(state)), 'tmp': tmp_path, 'state': state}


def make_fake_game(game_dir, files=None):
    """A ReStreet root: Game/data0.big (what marks a game folder) + the given files + online-patch.json."""
    files = {'Game/data0.big': b'db', **(files or {})}
    for rel, data in files.items():
        path = game_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (game_dir / 'online-patch.json').write_text('{"PatchVersion": "2.0.8-online"}')


def make_fake_save(save_dir):
    """A FIFA Street save: 00000001/Settings X/Settings X + Headers/00000001/Settings X.header."""
    (save_dir / '00000001' / 'Settings X').mkdir(parents=True)
    (save_dir / '00000001' / 'Settings X' / 'Settings X').write_text('save')
    (save_dir / 'Headers' / '00000001').mkdir(parents=True)
    (save_dir / 'Headers' / '00000001' / 'Settings X.header').write_text('header')


def palmeiras_v2(client):
    """Palmeiras fixture as a v2 project, with its crest uploaded through the API."""
    import json
    from fsmod import model
    with open(os.path.join(FIXTURE, 'project_v1.json'), encoding='utf-8') as f:
        project = model.from_v1(json.load(f))
    with open(os.path.join(FIXTURE, 'escudo_palmeiras.png'), 'rb') as f:
        r = client.post('/api/images', files={'file': ('escudo palmeiras.png', f, 'image/png')})
    assert r.status_code == 200, r.text
    project.teams[0].crest = r.json()['path']
    return project.to_json(), r.json()
