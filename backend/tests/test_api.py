import io
import json
import os

import pytest
from conftest import FIXTURE, palmeiras_v2
from PIL import Image

from fsapi import settings


def test_status_reports_empty_project(env):
    r = env['client'].get('/api/status')
    assert r.status_code == 200
    body = r.json()
    assert body['original_files']['missing'] == []
    assert body['project']['exists'] is False
    assert body['patch']['built'] is False


def test_catalog_and_originals(env):
    c = env['client']
    cat = c.get('/api/catalog').json()
    assert 'slots' not in cat
    assert 'free_leagues' not in cat
    assert len(cat['appearance']['headtypecode']) > 100
    leagues = c.get('/api/originals/leagues').json()
    assert any(lg['id'] == 53 for lg in leagues)
    barca = c.get('/api/originals/players', params={'team': 241}).json()
    assert 1 <= barca['total'] <= 13
    assert c.get('/api/originals/players', params={'q': 'messi'}).json()['total'] >= 1


def test_original_crests_and_photos_are_cached_on_disk(env):
    c = env['client']
    teams = {t['id']: t for t in c.get('/api/originals/teams').json()}
    assert teams[1]['crest'] and not teams[111592]['crest']  # Arsenal; Free Agents (internal team, no crest)
    players = c.get('/api/originals/players', params={'limit': 5000}).json()['items']
    with_photo = next(p['id'] for p in players if p['photo'])
    without = next(p['id'] for p in players if not p['photo'])

    r = c.get('/api/originals/crests/1.webp')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    assert Image.open(io.BytesIO(r.content)).size == (128, 128)
    assert c.get('/api/originals/crests/111592.webp').status_code == 404
    assert c.get(f'/api/originals/photos/{with_photo}.webp').status_code == 200
    assert c.get(f'/api/originals/photos/{without}.webp').status_code == 404

    cache = env['tmp'] / 'cache' / 'originals'
    (folder,) = cache.iterdir()
    assert sorted(p.name for p in (folder / 'crests').iterdir()) == ['1.webp']
    (folder / 'crests' / '1.webp').write_bytes(b'cached')  # the second request reads the cache
    assert c.get('/api/originals/crests/1.webp').content == b'cached'

    stale = cache / 'old-originals'
    stale.mkdir()
    env['state'].load_game(env['state'].game.folder)  # originals imported again: other cache folders go away
    c.get('/api/originals/crests/1.webp')
    assert not stale.exists()

def test_crest_upload_stores_the_image(env):
    _, upload = palmeiras_v2(env['client'])
    assert upload == {'path': upload['path']} and upload['path'].startswith('images/')
    name = upload['path'].split('/', 1)[1]
    assert env['client'].get(f'/api/images/{name}').status_code == 200
    assert env['client'].get('/api/images/..%2Fdatabase.json').status_code in (400, 404)


def test_save_project_returns_portuguese_issues(env):
    c = env['client']
    project, _ = palmeiras_v2(c)
    project['teams'][0]['abbreviation'] = 'PALM'
    r = c.put('/api/project', json=project)
    assert r.status_code == 200
    issues = [i for i in r.json()['issues'] if i['code'] != 'league_image_missing']  # the fixture league has none
    assert [i['code'] for i in issues] == ['text_too_long']
    defaults = r.json()['defaults']
    assert set(defaults) == {p['uid'] for p in project['players']}
    assert all('ATH' in d['skills'] and d['template'] for d in defaults.values())
    assert 'caracteres' in issues[0]['message']
    assert c.get('/api/project').json()['project']['teams'][0]['abbreviation'] == 'PALM'


def test_invalid_shape_is_rejected(env):
    r = env['client'].put('/api/project', json={'teams': [{'uid': 'x', 'name': 'X', 'league': 10,
                                                          'primary_color': [300, 0, 0], 'secondary_color': [0, 0, 0]}]})
    assert r.status_code == 422


def test_build_refuses_project_with_errors(env):
    c = env['client']
    project, _ = palmeiras_v2(c)
    project['leagues'][0]['league_id'] = 382
    c.put('/api/project', json=project)
    r = c.post('/api/patch/build')
    assert r.status_code == 422
    assert r.json()['detail']['code'] == 'project_has_errors'


def test_build_then_install_into_a_fake_game(env):
    c, tmp = env['client'], env['tmp']
    project, _ = palmeiras_v2(c)
    project['teams'][0].pop('team_id', None)  # the build gives a new teamid and saves it
    c.put('/api/project', json=project)
    r = c.post('/api/patch/build')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['patch']['up_to_date'] is True
    prog = c.get('/api/patch/progress').json()  # what the screen polls while building
    assert not prog['running'] and prog['error'] is None and prog['step'] == 'files' and prog['done'] == prog['total']
    assert prog['steps'][0] == 'database' and prog['elapsed'] >= 0
    saved = c.get('/api/project').json()['project']
    assert saved['teams'][0]['team_id'] == body['assigned_team_ids']['tm_01'] == 150000
    ids = {p['uid']: p['player_id'] for p in saved['players']}  # playerids given by the build are kept
    assert ids == body['assigned_player_ids'] and len(set(ids.values())) == len(ids)
    files = {f.lower() for f in body['patch']['files']}
    assert {'game/data/loc/locale.big', 'game/data/loc/locale_ptbr.big', 'game/data/ui/imgassets/heads/2dheads.bh',
            'game/data/ui/imgassets/heads/2dheads.big', 'game/data1.bh', 'game/data1.big', 'game/data3.bh',
            'game/data3.big', 'game/data7.bh', 'game/data7.big', 'game/data8.bh', 'game/data8.big'} < files
    assert {'game/data/ui/imgassets/crest/licensed_large/l150000.dds',
            'game/data/sceneassets/kit/kit_150000_0_0.rx3'} < files  # team files are loose
    assert c.get('/api/status').json()['patch']['up_to_date'] is True

    crest = c.get('/api/project').json()['project']['teams'][0]['crest']
    preview = c.get('/api/preview/kit.png', params={'jersey': '0,100,50', 'crest': crest})
    assert preview.status_code == 200 and preview.content[:4] == b'\x89PNG'

    r = c.post('/api/patch/install')
    assert r.status_code == 200, r.text
    report = r.json()
    game = tmp / 'game' / 'Game'
    for rel in body['patch']['files']:
        assert os.path.getsize(tmp / 'game' / rel) == os.path.getsize(env['state'].patch_dir + '/' + rel), rel
    assert (game / 'data8.big').read_bytes() == (tmp / 'patch' / 'Game' / 'data8.big').read_bytes()
    assert (game / '.fsmod_manifest.json').exists()
    save = env['state'].config.save_dir
    assert report['save_removed'] == 2 and os.listdir(save) == ['Headers']  # the save is deleted, no copy
    assert c.get('/api/status').json()['setup']['game'] == {
        'version': '2.0.8', 'tested': True, 'tested_versions': ['2.0.4', '2.0.8', '2.1.3'], 'installed': True, 'changed': []}
    (game / 'data8.bh').write_bytes(b'changed outside the app')
    assert c.get('/api/status').json()['setup']['game']['changed'] == ['data8.bh']

    # changing the project makes the patch outdated, and install refuses it
    project = c.get('/api/project').json()['project']
    project['teams'][0]['name'] = 'Palmeiras B'
    c.put('/api/project', json=project)
    assert c.get('/api/status').json()['patch']['up_to_date'] is False
    assert c.post('/api/patch/install').status_code == 409

    # uninstall: the app's originals come back, what the patch added goes away
    r = c.post('/api/patch/uninstall')
    assert r.status_code == 200, r.text
    assert (game / 'data1.big').stat().st_size == os.path.getsize(os.path.join(env['state'].game.folder, 'Game', 'data1.big'))
    assert not (game / 'data8.big').exists() and not (game / 'data' / 'sceneassets').exists()
    assert not (game / '.fsmod_manifest.json').exists()
    assert c.get('/api/status').json()['setup']['game']['installed'] is False
    assert c.post('/api/patch/uninstall').json()['detail']['code'] == 'not_installed'


def test_player_photo_upload_and_preview(env):
    import io
    from PIL import Image
    c = env['client']
    buf = io.BytesIO()
    Image.new('RGBA', (200, 260), (30, 120, 200, 255)).save(buf, format='PNG')
    r = c.post('/api/images', params={'kind': 'photo'}, files={'file': ('rosto.png', buf.getvalue(), 'image/png')})
    assert r.status_code == 200, r.text
    body = r.json()
    assert list(body) == ['path']
    preview = c.get('/api/preview/photo.png', params={'path': body['path']})
    assert Image.open(io.BytesIO(preview.content)).size == (256, 256)


def test_reinstall_restores_files_that_left_the_patch(tmp_path):
    """A file installed before and no longer in the patch goes back to the original (original_files)."""
    from conftest import make_fake_game, make_fake_save
    from fsapi.patch_service import install

    def make(folder, files):
        for rel, data in files.items():
            path = tmp_path / folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    make('original', {'Game/data1.big': b'orig1', 'Game/data/loc/locale.big': b'origL'})
    make_fake_game(tmp_path / 'game', {'Game/data1.big': b'orig1', 'Game/data/loc/locale.big': b'origL',
                                       'Game/data8.big': b'other mod'})
    make('patch_a', {'patch.json': b'{}', 'Game/data8.big': b'db-a', 'Game/data1.big': b'mod1',
                     'Game/data/loc/locale.big': b'modL'})
    make('patch_b', {'patch.json': b'{}', 'Game/data8.big': b'db-b', 'Game/data/loc/locale.big': b'modL2'})
    save = tmp_path / 'fifastreet' / 'P' / '4541097B'
    args = dict(game_dir=str(tmp_path / 'game'), backups_dir=str(tmp_path / 'backups'),
                original_dir=str(tmp_path / 'original'), save_dir=str(save), check_running=False)
    make_fake_save(save)
    first = install(str(tmp_path / 'patch_a'), **args)
    game = tmp_path / 'game' / 'Game'
    assert (game / 'data1.big').read_bytes() == b'mod1'
    assert (tmp_path / 'backups' / os.path.basename(first['backup']) / 'data8.big').read_bytes() == b'other mod'
    report = install(str(tmp_path / 'patch_b'), **args)
    assert report['restored'] == ['data1.big'] and report['backup'] is None  # data8 is the app's now
    assert (game / 'data1.big').read_bytes() == b'orig1'
    assert (game / 'data' / 'loc' / 'locale.big').read_bytes() == b'modL2'
    assert (game / 'data8.big').read_bytes() == b'db-b'


def test_failed_install_puts_the_game_back(tmp_path, monkeypatch):
    """A copy that fails half way leaves the game as the originals (nothing half-installed, no manifest)."""
    from conftest import make_fake_game, make_fake_save
    from fsapi import patch_service

    original = tmp_path / 'original' / 'Game'
    original.mkdir(parents=True)
    (original / 'data1.big').write_bytes(b'orig1')
    make_fake_game(tmp_path / 'game', {'Game/data1.big': b'orig1'})
    patch = tmp_path / 'patch'
    for rel, data in {'patch.json': b'{}', 'Game/data1.big': b'mod1', 'Game/data8.big': b'db',
                      'Game/data9.big': b'boom'}.items():
        (patch / rel).parent.mkdir(parents=True, exist_ok=True)
        (patch / rel).write_bytes(data)
    real_copy = patch_service._copy_atomic

    def copy(src, dst):
        if src.endswith('data9.big'):
            raise OSError('disk unplugged')
        return real_copy(src, dst)
    monkeypatch.setattr(patch_service, '_copy_atomic', copy)
    save = tmp_path / 'fifastreet' / 'P' / '4541097B'
    make_fake_save(save)
    with pytest.raises(OSError):
        patch_service.install(str(patch), str(tmp_path / 'game'), str(tmp_path / 'backups'), str(tmp_path / 'original'),
                              str(save), check_running=False)
    game = tmp_path / 'game' / 'Game'
    assert (game / 'data1.big').read_bytes() == b'orig1'
    assert not (game / 'data8.big').exists() and not (game / '.fsmod_manifest.json').exists()
    assert (save / '00000001').exists()  # the save goes only when the install succeeds


def test_save_delete_only_touches_a_fifa_street_profile(env):
    from fsapi import game_setup
    c, state = env['client'], env['state']
    assert c.post('/api/save/delete').json() == {'removed': 2}
    assert c.post('/api/save/delete').json() == {'removed': 0}
    other = env['tmp'] / 'Documents'
    (other / '00000001').mkdir(parents=True)
    with pytest.raises(game_setup.SetupError):
        game_setup.delete_save(str(other))
    assert (other / '00000001').exists()
    state.config.save_dir = str(other)
    assert c.post('/api/save/delete').json()['detail']['code'] == 'save_dir_invalid'


def test_first_run_setup(env):
    """The setup screen: the game folder is checked, the notice must be accepted, the choices are saved."""
    c, state, tmp = env['client'], env['state'], env['tmp']
    assert c.get('/api/status').json()['setup']['required'] is False
    state.config.terms_version = None
    setup = c.get('/api/status').json()['setup']
    assert setup['required'] is True and setup['reasons'] == ['terms'] and setup['originals']['verified'] is True
    (tmp / 'game' / 'Game' / 'data8.big').write_bytes(b'a mod copied by hand')
    checked = c.post('/api/setup/check', json={'game_dir': state.config.game_dir}).json()
    assert checked['valid'] and checked['version'] == '2.0.8' and checked['tested']
    assert checked['files']['Game/data0.big'] == 'different' and checked['files']['Game/data1.big'] == 'missing'
    assert checked['files']['Game/data8.big'] == 'added' and 'Game/data8.bh' not in checked['files']
    assert not checked['official'] and not checked['app_patch'] and not checked['accepted']
    assert c.post('/api/setup/check', json={'game_dir': str(tmp)}).json()['valid'] is False
    req = {'game_dir': state.config.game_dir, 'save_dir': state.config.save_dir, 'terms_version': 0}
    assert c.post('/api/setup/apply', json=req).json()['detail']['code'] == 'terms_not_accepted'
    assert c.post('/api/setup/apply', json={**req, 'terms_version': 1, 'save_dir': str(tmp)}).json()['detail'][
        'code'] == 'save_dir_invalid'
    # a game whose files are not the official ones is refused, even though the app has its originals...
    refused = c.post('/api/setup/apply', json={**req, 'terms_version': 1}).json()['detail']
    assert refused['code'] == 'game_files_not_official' and refused['files']['Game/data1.big'] == 'missing'
    # ...unless what differs is a patch of this app (it can undo it)
    (tmp / 'game' / 'Game' / '.fsmod_manifest.json').write_text('{"version": 2, "files": {}}')
    assert c.post('/api/setup/check', json={'game_dir': state.config.game_dir}).json()['accepted'] is True
    r = c.post('/api/setup/apply', json={**req, 'terms_version': 1})
    assert r.status_code == 200, r.text
    assert r.json()['imported'] == [] and r.json()['setup']['required'] is False
    assert c.get('/api/config').json()['terms_version'] == 1


def test_originals_are_imported_only_when_official(tmp_path, monkeypatch):
    from conftest import make_fake_game
    from fsapi import game_setup
    files = {'Game/data0.big': b'db', 'Game/data1.big': b'one'}
    monkeypatch.setattr(game_setup, 'OFFICIAL_FILES', {
        rel: (len(data), __import__('hashlib').sha1(data).hexdigest()) for rel, data in files.items()})
    make_fake_game(tmp_path / 'game', {'Game/data1.big': b'one'})
    originals = game_setup.Originals(str(tmp_path / 'mine'), str(tmp_path / 'prints.json'))
    assert originals.state()['missing'] == sorted(files)
    assert originals.import_from(str(tmp_path / 'game')) == sorted(files)
    assert originals.state()['verified'] and (tmp_path / 'mine' / 'Game' / 'data1.big').read_bytes() == b'one'
    assert originals.import_from(str(tmp_path / 'game')) == []  # already there
    (tmp_path / 'mine' / 'Game' / 'data1.big').write_bytes(b'mod')
    assert originals.state()['modified'] == ['Game/data1.big']
    (tmp_path / 'game' / 'Game' / 'data1.big').write_bytes(b'mod')  # a game with a mod is never imported
    with pytest.raises(game_setup.SetupError):
        originals.import_from(str(tmp_path / 'game'))


def test_images_get_the_fixed_name_of_their_entity_on_save(env):
    import re
    from fsapi.project_store import file_slug
    assert file_slug(' São: Paulo/FC? ') == 'São-PauloFC'
    c, folder = env['client'], env['state'].store.folder
    images = os.path.join(folder, 'images')
    project, upload = palmeiras_v2(c)
    assert re.fullmatch(r'images/upload-[0-9a-f]{12}\.png', upload['path']), upload  # provisional until saved
    with open(os.path.join(FIXTURE, 'escudo_palmeiras.png'), 'rb') as f:
        data = f.read()
    photo = c.post('/api/images', files={'file': ('x.PNG', data, 'image/png')}).json()['path']
    c.post('/api/images', files={'file': ('abandoned.png', data, 'image/png')})  # uploaded, then discarded
    team, player = project['teams'][0], project['players'][0]
    player['photo'] = photo
    saved = c.put('/api/project', json=project).json()['project']
    assert saved['teams'][0]['crest'] == f"images/teams/team-{team['uid']}.png"
    assert saved['players'][0]['photo'] == f"images/players/player-{player['uid']}.png"
    assert sorted(os.listdir(images)) == ['players', 'teams']
    assert os.listdir(os.path.join(images, 'teams')) == [f"team-{team['uid']}.png"]
    assert os.listdir(os.path.join(images, 'players')) == [f"player-{player['uid']}.png"]

    # replacing an image: the upload takes the fixed name (same name, new bytes) and the old file goes away
    hash_before = env['state'].store.content_hash()
    webp = io_image('WEBP')
    saved['teams'][0]['crest'] = c.post('/api/images', files={'file': ('new.webp', webp, 'image/webp')}).json()['path']
    saved = c.put('/api/project', json=saved).json()['project']
    assert saved['teams'][0]['crest'] == f"images/teams/team-{team['uid']}.webp"
    assert os.listdir(os.path.join(images, 'teams')) == [f"team-{team['uid']}.webp"]
    assert env['state'].store.content_hash() != hash_before

    # a copied team keeps the original's crest: it gets its own file
    saved['teams'].append({**saved['teams'][0], 'uid': 'tm_copy', 'team_id': None, 'captain': None})
    saved = c.put('/api/project', json=saved).json()['project']
    assert saved['teams'][1]['crest'] == 'images/teams/team-tm_copy.webp'
    assert os.path.isfile(os.path.join(images, 'teams', f"team-{team['uid']}.webp"))

    # removing the photo deletes its file; the response headers make the browser revalidate replaced images
    saved['players'][0]['photo'] = None
    c.put('/api/project', json=saved)
    assert not os.path.exists(os.path.join(images, 'players'))  # the empty kind folder goes too
    assert c.get('/api/images/teams/team-tm_copy.webp').headers['cache-control'] == 'no-cache'


def test_real_kit_images_are_named_by_team_and_slot(env):
    c, folder = env['client'], env['state'].store.folder
    kits = os.path.join(folder, 'images', 'teams', 'kits')
    project, _ = palmeiras_v2(c)
    team = project['teams'][0]
    up = lambda: c.post('/api/images', files={'file': ('k.png', io_image('PNG'), 'image/png')}).json()['path']
    team['use_real_kits'] = True
    team['real_kits'] = {'home': {'jersey': up(), 'shorts': up(), 'thumbnail': up()}, 'goalkeeper': {'jersey': up()}}
    saved = c.put('/api/project', json=project).json()
    uid = team['uid']
    assert saved['project']['teams'][0]['real_kits']['home']['jersey'] == f'images/teams/kits/team-{uid}-home-jersey.png'
    assert sorted(os.listdir(kits)) == sorted(f'team-{uid}-{n}.png' for n in
                                              ('home-jersey', 'home-shorts', 'home-thumbnail', 'goalkeeper-jersey'))
    codes = {(i['field'], i['code']) for i in saved['issues'] if i['entity'] == uid}
    assert ('real_kits.goalkeeper.shorts', 'real_kit_file_required') in codes
    assert ('real_kits.away', 'real_kit_missing') in codes
    assert ('real_kits.home.jersey', 'real_kit_small') in codes  # square, but far below 1024
    assert ('real_kits.home.shorts', 'real_kit_bad_size') in codes  # 8x8 is not 2:1

    # a slot cleared and a file removed: their images go away on save, nothing left orphan
    project = saved['project']
    del project['teams'][0]['real_kits']['goalkeeper']
    project['teams'][0]['real_kits']['home']['thumbnail'] = None
    c.put('/api/project', json=project)
    assert sorted(os.listdir(kits)) == [f'team-{uid}-home-jersey.png', f'team-{uid}-home-shorts.png']


def io_image(fmt):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (8, 8), (255, 0, 0, 255)).save(buf, format=fmt)
    return buf.getvalue()


def test_faces_of_players_without_a_face_are_deleted_on_save(env):
    c, folder = env['client'], env['state'].store.folder
    project, _ = palmeiras_v2(c)
    kept, gone = project['players'][0]['uid'], 'jg_removed'
    for uid in (kept, gone):
        os.makedirs(os.path.join(folder, 'faces', uid))
    project['players'][0].update(generic=True, face={'source_id': 1, 'pack': 'x'})  # face kept while generic
    c.put('/api/project', json=project)
    assert os.listdir(os.path.join(folder, 'faces')) == [kept]


def test_old_project_layout_is_upgraded(tmp_path):
    import json
    from fsapi.project_store import ProjectStore, migrate_folder
    old, new = tmp_path / 'projeto', tmp_path / 'project'
    (old / 'images').mkdir(parents=True)
    (old / '.gitkeep').write_text('')
    (old / 'images' / 'team-Palmeiras-2026-10-20T14-03-05.123Z.png').write_bytes(b'crest')
    (old / 'images' / 'player-Orphan-2026-10-20T14-03-05.123Z.png').write_bytes(b'old')
    project = {'version': 2, 'leagues': [], 'players': [], 'teams': [
        {'uid': 'tm_01', 'name': 'Palmeiras', 'league': 53, 'primary_color': [0, 0, 0], 'secondary_color': [255, 255, 255],
         'crest': 'images/team-Palmeiras-2026-10-20T14-03-05.123Z.png'}]}
    (old / 'projeto.json').write_text(json.dumps(project), encoding='utf-8')
    assert migrate_folder(str(old), str(new)) and not old.exists()
    store = ProjectStore(str(new))
    assert store.upgrade() and not store.upgrade()
    assert sorted(os.listdir(new)) == ['database.json', 'images']
    assert os.listdir(new / 'images') == ['teams'] and os.listdir(new / 'images' / 'teams') == ['team-tm_01.png']
    assert store.load().teams[0].crest == 'images/teams/team-tm_01.png'
    assert not migrate_folder(str(old), str(new))  # nothing left to move


def test_head_preview_assets(env):
    c = env['client']
    assert c.get('/api/preview/head/10.glb').content[:4] == b'glTF'
    assert c.get('/api/preview/hair/10.glb').content[:4] == b'glTF'
    assert c.get('/api/preview/hair/0.glb').status_code == 404
    assert c.get('/api/preview/hair/10/color.png').status_code == 200
    assert c.get('/api/preview/hair/10/strands.png').content[:4] == b'\x89PNG'
    assert c.get('/api/preview/eyes/3.png').content[:4] == b'\x89PNG'
    assert c.get('/api/preview/face.png', params={'facialhairtypecode': 6, 'skintonecode': 9}).content[:4] == b'\x89PNG'
    assert c.get('/api/preview/head/99999.glb').status_code == 404
    assert c.get('/api/catalog').json()['hair_colors']['1'] == '#0e0e0d'


def test_body_preview_assets(env):
    c = env['client']
    assert c.get('/api/preview/body/shoes/600.glb').content[:4] == b'glTF'
    assert c.get('/api/preview/body/legs/2.glb').content[:4] == b'glTF'
    assert c.get('/api/preview/body/hat/0.glb').status_code == 422
    assert c.get('/api/preview/body/legs/9.glb').status_code == 404
    assert c.get('/api/preview/skin/9.png').content[:4] == b'\x89PNG'
    assert c.get('/api/preview/glove/0.png').status_code == 200
    assert c.get('/api/preview/street/top/20/5.png').content[:4] == b'\x89PNG'
    assert c.get('/api/preview/body/top/24.glb').content[:4] == b'glTF'
    cat = c.get('/api/catalog').json()
    assert cat['street_options']['top']['20'] and cat['template_street']['112298']['home']['top']['style'] == 20
    assert c.get('/api/preview/body/gloves/0.glb').content[:4] == b'glTF'
    assert c.get('/api/preview/shoe/503.png').content[:4] == b'\x89PNG'
    assert c.get('/api/preview/kit/jersey.png', params={'color': '10,20,200'}).content[:4] == b'\x89PNG'
    assert c.get('/api/preview/kit/socks.png', params={'color': '10,20,200'}).status_code == 422


def test_real_face_from_a_pack(env):
    """FIFA 14 pack read in place: gallery, converted preview, copy into the project, validation."""
    from fsmod import facepack
    pack = os.path.join(settings.REPO_DIR, 'Faces', 'various-by-Colgado')  # local face pack (outside git)
    if not facepack.assets_dir(pack):
        pytest.skip('face pack not available')
    c, state = env['client'], env['state']
    face_ids = lambda r: {f['id'] for f in r.json()['faces']}  # noqa: E731 (no count: the pack grows)
    r = c.get('/api/facepack', params={'folder': pack})
    assert r.status_code == 200 and 274254 in face_ids(r)
    face = next(f for f in r.json()['faces'] if f['id'] == 274254)
    assert face['player'] is None  # no players base in the settings: the face shows only its id
    base = env['tmp'] / 'players.json'
    base.write_text(json.dumps({'players': {'274254': {'name': 'Dorny Romero', 'club': 'X', 'extra': 1}}}), 'utf-8')
    state.config.players_base_file = str(base)
    face = next(f for f in c.get('/api/facepack', params={'folder': pack}).json()['faces'] if f['id'] == 274254)
    assert face['player'] == {'name': 'Dorny Romero', 'club': 'X'}  # who the face is, from the players base
    assert c.get('/api/facepack').json()['detail']['code'] == 'facepack_not_set'  # not set in the settings yet
    state.config.face_pack_dir = pack
    assert 274254 in face_ids(c.get('/api/facepack'))  # the folder of the settings
    assert c.get('/api/facepack', params={'folder': str(env['tmp'])}).json()['detail']['code'] == 'facepack_not_found'
    assert c.get('/api/facepack/thumb.png', params={'folder': pack, 'face': 274254}).content[:4] == b'\x89PNG'

    project, _ = palmeiras_v2(c)
    uid = project['players'][0]['uid']
    r = c.post('/api/facepack/use', json={'folder': pack, 'face_id': 274254, 'player': uid})
    assert r.json() == {'face': {'source_id': 274254, 'pack': 'various-by-Colgado'}}
    assert os.path.isfile(os.path.join(state.store.folder, 'faces', uid, 'heads', 'head_274254_0.rx3'))
    project['players'][0].update(generic=False, face=r.json()['face'])
    codes = {(i['code'], i['entity']) for i in c.put('/api/project', json=project).json()['issues']}
    assert not [code for code, entity in codes if entity == uid and code.startswith('face')]
    project['players'][1]['generic'] = False
    codes = {(i['code'], i['entity']) for i in c.post('/api/project/validate', json=project).json()['issues']}
    assert ('face_missing', project['players'][1]['uid']) in codes
    copy = {'from_player': uid, 'to_player': 'jg_copy', 'face_id': 274254}  # "Copy" of a player
    assert c.post('/api/faces/copy', json=copy).status_code == 200
    assert os.path.isfile(os.path.join(state.store.folder, 'faces', 'jg_copy', 'heads', 'head_274254_0.rx3'))
    assert c.post('/api/faces/copy', json={**copy, 'to_player': '../x'}).status_code == 422
    assert c.post('/api/faces/copy', json={**copy, 'from_player': 'jg_none'}).status_code == 404

    q = {'player': uid, 'face': 274254, 'haircolor': 3}
    for asset in ('head.glb', 'hairlod.glb', 'face.png', 'strands.png'):
        r = c.get(f'/api/preview/scanned/{asset}', params=q)
        assert r.status_code == 200, asset
    bare = c.get('/api/preview/scanned/face.png', params={**q, 'paint': 'false'})  # "Pintar a raiz do cabelo" off
    assert bare.status_code == 200 and bare.content != c.get('/api/preview/scanned/face.png', params=q).content
    assert c.get('/api/preview/lodhead.glb').content[:4] == b'glTF'



def test_players_base_check_explains_what_breaks_the_contract(env, tmp_path):
    c = env['client']

    def check(data):
        path = tmp_path / f'base{len(list(tmp_path.iterdir()))}.json'
        path.write_text(data if isinstance(data, str) else json.dumps(data), 'utf-8')
        return c.post('/api/players-base/check', json={'file': str(path)})

    assert check({'players': {'1': {'name': 'A'}, '2': {'name': 'B', 'club': 'C'}, '3': {}}}).json() ==         {'players': 2, 'skipped': 0, 'problems': []}  # {} = id nobody has data for yet: not a problem
    r = check({'players': {'1': {'name': 'A'}, '2': {'player_name': 'B'}, 'x': {'name': 'C'}}})
    assert r.json()['players'] == 1 and r.json()['skipped'] == 2
    assert any('"name"' in p and 'player_name' in p for p in r.json()['problems'])  # says which field it expected
    for data, code in (('{bad', 'players_base_invalid_json'), ({'jogadores': {}}, 'players_base_no_players'),
                       ({'players': [{'name': 'A'}]}, 'players_base_players_not_object')):
        r = check(data)
        assert r.status_code == 400 and r.json()['detail']['code'] == code
    assert c.post('/api/players-base/check', json={'file': str(tmp_path / 'none.json')}).json()['detail']['code'] ==         'players_base_not_found'


def test_players_base_search_and_record_for_a_player(env, tmp_path):
    c = env['client']
    assert c.get('/api/players-base/players').json()['detail']['code'] == 'players_base_not_set'
    base = tmp_path / 'players.json'
    base.write_text(json.dumps({'players': {
        '55607': {'name': 'Edwuin Pernía', 'club': 'Puerto Cabello', 'first_name': 'Edwuin', 'last_name': 'Pernía',
                  'birth_date': '1995-01-02', 'height_cm': 180, 'weight_kg': 75, 'preferred_foot': 'Left'},
        '1': {'name': 'Other', 'height_cm': 'tall', 'preferred_foot': 'Both', 'birth_date': '02/01/1995'}}}), 'utf-8')
    env['state'].config.players_base_file = str(base)
    assert [p['id'] for p in c.get('/api/players-base/players', params={'q': 'pernia'}).json()['items']] == [55607]
    assert c.get('/api/players-base/players', params={'q': 'cabello'}).json()['total'] == 1  # club too
    assert c.get('/api/players-base/players/55607').json()['preferred_foot'] == 'Left'
    assert c.get('/api/players-base/players/1').json() == {'id': 1, 'name': 'Other'}  # invalid values are not offered
    assert c.get('/api/players-base/players/2').status_code == 404


def test_players_base_record_converts_skills_and_nationality(env, tmp_path):
    from fsapi.ea_players import ATTRIBUTES
    c = env['client']
    attrs = {a: 50 for a in ATTRIBUTES} | {'acceleration': 20, 'sprint_speed': 20, 'gk_diving': 80}
    attrs.pop('defensive_awareness')  # older editions: falls back to standing_tackle and interceptions
    base = tmp_path / 'players.json'
    base.write_text(json.dumps({'players': {
        '10': {'name': 'Keeper', 'nationality': "Côte d'Ivoire", 'positions': ['GK'], 'skill_moves': 5,
               'attributes': attrs},
        '11': {'name': 'Partial', 'nationality': 'Atlantis', 'attributes': {'finishing': 90}}}}), 'utf-8')
    env['state'].config.players_base_file = str(base)
    rec = c.get('/api/players-base/players/10').json()
    assert rec['nation_id'] == 108  # Ivory Coast in the game
    # SPE 20 lifted to the keepers' floor; GK = mean of 80, 50, 50, 50; TRI = skill moves 5 + 1, capped at 4
    assert rec['skills'] == {'ATH': 50, 'DEF': 50, 'DRI': 50, 'GK': 58, 'PAS': 50, 'SHO': 50, 'SPE': 45, 'TRI': 4}
    partial = c.get('/api/players-base/players/11').json()
    assert 'skills' not in partial and 'nation_id' not in partial

def test_original_stadiums_and_changes_round_trip(env):
    c = env['client']
    stadiums = c.get('/api/originals/stadiums').json()
    assert len(stadiums) == 22 and all(s['locked'] for s in stadiums)
    teams = {t['id']: t for t in c.get('/api/originals/teams').json()}
    assert teams[112339]['lockable'] and teams[112339]['locked'] and not teams[241]['lockable']
    project, _ = palmeiras_v2(c)
    project['originals'] = {'hidden_leagues': [39], 'hidden_teams': [243], 'team_locks': {'112339': False},
                            'stadium_locks': {str(stadiums[0]['id']): False}}
    r = c.put('/api/project', json=project)
    assert r.status_code == 200 and not [i for i in r.json()['issues'] if i['severity'] == 'error']
    assert r.json()['project']['originals']['team_locks'] == {'112339': False}
    project['originals']['team_locks'] = {'241': True}
    codes = [i['code'] for i in c.post('/api/project/validate', json=project).json()['issues']]
    assert 'original_team_not_lockable' in codes


def test_export_patch_zips_the_game_folder(tmp_path):
    import zipfile
    from fsapi.patch_service import InstallError, export_patch
    patch = tmp_path / 'patch'
    with pytest.raises(InstallError):
        export_patch(str(patch), str(tmp_path / 'x.zip'))
    for rel, data in {'patch.json': b'{}', 'Game/data8.big': b'db', 'Game/data/loc/locale.big': b'loc'}.items():
        (patch / rel).parent.mkdir(parents=True, exist_ok=True)
        (patch / rel).write_bytes(data)
    r = export_patch(str(patch), str(tmp_path / 'out.zip'))
    assert r['files'] == 2
    with zipfile.ZipFile(tmp_path / 'out.zip') as z:  # copied over the game root as is
        assert sorted(z.namelist()) == ['Game/data/loc/locale.big', 'Game/data8.big']
        assert z.read('Game/data8.big') == b'db'


def test_backup_zip_round_trip(env):
    import io
    import zipfile
    c, folder = env['client'], env['state'].store.folder
    project, _ = palmeiras_v2(c)
    uid = project['players'][0]['uid']
    os.makedirs(os.path.join(folder, 'faces', uid, 'heads'))
    with open(os.path.join(folder, 'faces', uid, 'heads', 'head_1_0.rx3'), 'wb') as f:
        f.write(b'face')
    project['players'][0]['face'] = {'source_id': 1, 'pack': 'x'}
    saved = c.put('/api/project', json=project).json()['project']
    r = c.get('/api/project/backup')
    assert r.status_code == 200 and 'attachment' in r.headers['content-disposition']
    backup = r.content
    names = sorted(zipfile.ZipFile(io.BytesIO(backup)).namelist())
    assert names == sorted(['database.json', saved['teams'][0]['crest'], f'faces/{uid}/heads/head_1_0.rx3'])

    # another project replaces it; restoring the backup brings back the JSON, the images and the faces
    c.put('/api/project', json={'version': 2, 'leagues': [], 'teams': [], 'players': []})
    assert os.listdir(os.path.join(folder, 'images')) == []
    r = c.post('/api/project/restore', files={'file': ('backup.zip', backup, 'application/zip')})
    assert r.status_code == 200, r.text
    assert r.json()['project'] == saved
    assert os.path.isfile(os.path.join(folder, saved['teams'][0]['crest']))
    assert os.path.isfile(os.path.join(folder, 'faces', uid, 'heads', 'head_1_0.rx3'))

    # the zip of the folder itself (project/...) also works; junk next to it is left out
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(backup)) as src, zipfile.ZipFile(buf, 'w') as z:
        for n in src.namelist():
            z.writestr(f'project/{n}', src.read(n))
        z.writestr('project/notes.txt', 'x')
    assert c.post('/api/project/restore', files={'file': ('b.zip', buf.getvalue())}).status_code == 200
    assert sorted(os.listdir(folder)) == ['database.json', 'faces', 'images']


@pytest.mark.parametrize('entries, reason', [
    (None, 'not_a_zip'),
    ({'images/a.png': b'x'}, 'no_database'),
    ({'database.json': b'{"version": 2, "leagues": "x"}'}, 'invalid_database'),
    ({'database.json': b'{"version": 2}', 'images/../../evil.png': b'x'}, 'unsafe_path'),
])
def test_bad_backups_leave_the_project_alone(env, entries, reason):
    import io
    import zipfile
    c = env['client']
    project, _ = palmeiras_v2(c)
    saved = c.put('/api/project', json=project).json()['project']
    data = b'not a zip'
    if entries is not None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            for n, d in entries.items():
                z.writestr(n, d)
        data = buf.getvalue()
    r = c.post('/api/project/restore', files={'file': ('b.zip', data)})
    assert r.status_code == 400 and r.json()['detail']['reason'] == reason, r.text
    assert c.get('/api/project').json()['project'] == saved


def test_editing_an_original_team_starts_from_the_game_and_survives_saving(env):
    from fsmod import model, original_team
    c = env['client']
    r = c.post('/api/originals/teams/241/edit', params={'uid': 'tm_barca'})
    assert r.status_code == 200
    team = r.json()
    assert team['original_id'] == 241 and team['league'] == 53 and team['crest'].startswith('images/upload-')
    assert set(team['real_kits']) == {'home', 'away', 'goalkeeper'} and team['loaded']['images']['crest']
    assert c.post('/api/originals/teams/999999/edit', params={'uid': 'x'}).status_code == 404

    r = c.put('/api/project', json={'version': 2, 'teams': [team]})
    assert r.status_code == 200 and not [i for i in r.json()['issues'] if i['severity'] == 'error']
    saved = model.Team.model_validate(r.json()['project']['teams'][0])
    assert saved.crest.startswith('images/teams/team-tm_barca')  # fixed names: still unchanged (by content)
    assert not original_team.changes(saved, str(env['tmp'] / 'project')).any


def test_real_kit_preview_prints_name_and_numbers(env):
    c = env['client']
    team = c.post('/api/originals/teams/241/edit', params={'uid': 'tm_barca'}).json()
    home = team['real_kits']['home']
    loaded = team['loaded']['images']['real_kits.home.jersey']
    plain = c.get('/api/preview/real-kit/jersey.png', params={'image': home['jersey']}).content
    printed = c.get('/api/preview/real-kit/jersey.png', params={
        'image': home['jersey'], 'number': 5, 'name': 'Puyol', 'team': 241, 'kind': 0, 'name_color': '240,218,40',
        'number_color': 5, 'jersey': home['jersey'], 'loaded': loaded})
    assert printed.status_code == 200 and printed.content != plain
    shorts = dict(image=home['shorts'], number=5, team=241, number_color=5, shorts_number_color=5)
    without = c.get('/api/preview/real-kit/shorts.png', params=shorts).content
    with_number = c.get('/api/preview/real-kit/shorts.png', params={**shorts, 'shorts_number': True}).content
    assert with_number != without


def test_editing_an_original_player_and_converting_old_game_links(env):
    """Editing one of the game's players starts from the game; a project saved with Team.game_players and
    TeamLink.replaces (29/10) gets entries for those game players when it is opened."""
    import json
    from fsmod import model, original_player
    c = env['client']
    r = c.post('/api/originals/players/158023/edit', params={'uid': 'jg_messi'})
    assert r.status_code == 200
    messi = r.json()
    assert messi['original_id'] == 158023 and len(messi['teams']) == 5 and messi['photo'].startswith('images/upload-')
    assert c.post('/api/originals/players/1/edit', params={'uid': 'x'}).status_code == 404
    r = c.put('/api/project', json={'version': 2, 'players': [messi]})
    assert r.status_code == 200 and not [i for i in r.json()['issues'] if i['severity'] == 'error']
    saved = model.Player.model_validate(r.json()['project']['players'][0])
    assert not original_player.changes(saved, str(env['tmp'] / 'project')).any
    assert c.get('/api/preview/game-head/158023/head.glb').status_code == 200

    old = {'version': 2, 'teams': [{'uid': 'tm_a', 'name': 'A', 'league': 39, 'primary_color': [0, 0, 0],
                                    'secondary_color': [1, 1, 1], 'game_players': [{'player_id': 158023, 'number': 30}]},
                                   {'uid': 'tm_barca', 'original_id': 241, 'name': 'B', 'league': 53,
                                    'primary_color': [0, 0, 0], 'secondary_color': [1, 1, 1],
                                    'takers': {'penalty': 10535}}],
           'players': [{'uid': 'jg_x', 'first_name': 'X', 'last_name': 'Y',
                        'teams': [{'team': 241, 'replaces': 10535}]}]}
    with open(env['tmp'] / 'project' / 'database.json', 'w', encoding='utf-8') as f:
        json.dump(old, f)
    project = c.get('/api/project').json()['project']
    assert 'game_players' not in project['teams'][0]
    entries = {p.get('original_id'): p for p in project['players']}
    assert {'team': 'tm_a', 'number': 30} in [{k: v for k, v in lk.items() if k in ('team', 'number')}
                                             for lk in entries[158023]['teams']]
    assert 241 not in [lk['team'] for lk in entries[10535]['teams']]
    assert project['players'][0]['teams'] == [{'team': 241}]
    assert project['teams'][1]['takers'] == {'penalty': 'jg_x'}  # the set piece went to the player who joined
