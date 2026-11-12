"""Leagues, teams and players shared in a zip (share_service) and the dates every entry keeps (created_at /
updated_at, set when the project is saved)."""
import io
import json
import os
import zipfile

import pytest
from PIL import Image

from fsmod import model, scanface


def png(color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new('RGB', (64, 32), color).save(buf, format='PNG')
    return buf.getvalue()


def image(client, color=(200, 30, 30), name='picture.png'):
    r = client.post('/api/images', files={'file': (name, png(color), 'image/png')})
    assert r.status_code == 200, r.text
    return r.json()['path']


def save(client, project):
    r = client.put('/api/project', json=project)
    assert r.status_code == 200, r.text
    return r.json()['project']


def team(uid='t1', leagues=('l1',), **extra):
    return {'uid': uid, 'name': 'Batata FC', 'leagues': list(leagues), 'primary_color': [10, 20, 30],
            'secondary_color': [240, 240, 240], **extra}


def player(uid='p1', teams=(('t1', 10),), **extra):
    return {'uid': uid, 'first_name': 'Diego', 'last_name': 'Silva',
            'teams': [{'team': t, 'number': n} for t, n in teams], **extra}


def export(client, kind, uids):
    r = client.post(f'/api/share/{kind}/export', json={'uids': uids})
    assert r.status_code == 200, r.text
    return r.content


def inspect(client, kind, data, name='share.zip'):
    return client.post(f'/api/share/{kind}/inspect', files={'file': (name, data, 'application/zip')})


def import_all(client, kind, data):
    r = inspect(client, kind, data)
    assert r.status_code == 200, r.text
    found = r.json()
    r = client.post(f'/api/share/{kind}/apply', json={'token': found['token'],
                                                      'uids': [i['uid'] for i in found['items']]})
    assert r.status_code == 200, r.text
    return found, r.json()['items']


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------- dates
def test_saving_stamps_created_and_updated(env, monkeypatch):
    client = env['client']
    monkeypatch.setattr('fsapi.main.now_iso', lambda: '2026-11-09T10:00:00Z')
    saved = save(client, {'leagues': [{'uid': 'l1', 'name': 'Liga'}]})
    league = saved['leagues'][0]
    assert league['created_at'] == league['updated_at'] == '2026-11-09T10:00:00Z'
    assert saved['version'] == model.CONTRACT_VERSION

    monkeypatch.setattr('fsapi.main.now_iso', lambda: '2026-11-10T10:00:00Z')
    same = save(client, saved)['leagues'][0]  # nothing changed: dates stay
    assert same['updated_at'] == '2026-11-09T10:00:00Z'
    without = dict(saved['leagues'][0])
    del without['created_at'], without['updated_at']  # a client that drops them does not lose them
    assert save(client, {'leagues': [without]})['leagues'][0]['created_at'] == '2026-11-09T10:00:00Z'

    changed = save(client, {'leagues': [{**league, 'name': 'Liga Nova'}]})['leagues'][0]
    assert changed['created_at'] == '2026-11-09T10:00:00Z' and changed['updated_at'] == '2026-11-10T10:00:00Z'


def test_imported_entries_keep_their_dates(env, monkeypatch):
    client = env['client']
    monkeypatch.setattr('fsapi.main.now_iso', lambda: '2026-11-10T10:00:00Z')
    saved = save(client, {'leagues': [{'uid': 'l1', 'name': 'Liga', 'created_at': '2026-01-01T00:00:00Z',
                                       'updated_at': '2026-02-01T00:00:00Z'}]})
    assert saved['leagues'][0]['created_at'] == '2026-01-01T00:00:00Z'
    assert saved['leagues'][0]['updated_at'] == '2026-02-01T00:00:00Z'


def test_a_project_from_before_the_dates_opens_and_saves(env):
    client, state = env['client'], env['state']
    os.makedirs(state.store.folder, exist_ok=True)
    with open(state.store.path, 'w', encoding='utf-8') as f:
        json.dump({'version': 8, 'leagues': [{'uid': 'l1', 'name': 'Liga'}]}, f)
    loaded = client.get('/api/project').json()['project']
    assert loaded['leagues'][0].get('created_at') is None
    saved = save(client, loaded)
    assert saved['version'] == model.CONTRACT_VERSION
    assert saved['leagues'][0].get('created_at') is None  # unchanged: no date made up


# ---------------------------------------------------------------- zip
def test_league_round_trip_keeps_uid_and_files(env):
    client = env['client']
    saved = save(client, {'leagues': [{'uid': 'l1', 'name': 'Liga Batata', 'image': image(client), 'league_id': 900,
                                       'short_name': 'LB'}]})
    data = export(client, 'leagues', ['l1'])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['type'] == 'fs4-league' and manifest['version'] == 1 and set(manifest) == {'type', 'version', 'league'}
        item = manifest['league']
        assert item['uid'] == 'l1' and item['image'] == 'league-l1.png' and item['league_id'] is None
        assert 'wide_image' in item and item['wide_image'] is None  # every key, null when empty
        assert sorted(z.namelist()) == ['league-l1.png', 'manifest.json']

    save(client, {'leagues': []})
    found, items = import_all(client, 'leagues', data)
    assert found['problems'] == [] and found['items'][0]['uid'] == 'l1'
    league = items[0]
    assert league['uid'] == 'l1' and league['image'].startswith('images/upload-')
    assert league['created_at'] == saved['leagues'][0]['created_at']
    again = save(client, {'leagues': [league]})['leagues'][0]
    assert again['image'] == 'images/leagues/league-l1.png'
    with open(os.path.join(env['state'].store.folder, again['image']), 'rb') as f:
        assert f.read() == png()


def test_team_goes_with_its_links_and_kit_pictures(env):
    client = env['client']
    real = {'home': {'jersey': image(client, (1, 2, 3)), 'shorts': image(client, (4, 5, 6))}}
    save(client, {'leagues': [{'uid': 'l1', 'name': 'Liga'}],
                  'teams': [team(crest=image(client), real_kits=real, use_real_kits=True, captain='p1',
                                 takers={'penalty': 'p1'}, leagues=['l1', 13], kit_credits='Kit maker',
                                 kit_credits_url='kits.example.com')],
                  'players': [player()]})
    data = export(client, 'teams', ['t1'])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        item = json.loads(z.read('manifest.json'))['team']
        assert item['leagues'] == ['l1', 13] and item['captain'] == 'p1' and item['takers'] == {'penalty': 'p1'}
        assert item['real_kits']['home']['jersey'] == 'team-t1-home-jersey.png'
        assert 'players' not in item  # the roster lives in the players

    save(client, {})  # an empty project: the team's league and players are not there, its links come anyway
    _, items = import_all(client, 'teams', data)
    tm = items[0]
    assert tm['leagues'] == ['l1', 13] and tm['captain'] == 'p1'
    assert tm['real_kits']['home']['shorts'].startswith('images/upload-')
    assert (tm['kit_credits'], tm['kit_credits_url']) == ('Kit maker', 'https://kits.example.com')


def test_player_goes_with_his_face(env):
    client, folder = env['client'], env['state'].store.folder
    face_dir = scanface.project_face_dir(folder, 'p1')
    for kind in scanface.REQUIRED:
        path = os.path.join(face_dir, *scanface.FILES[kind].format(4242).split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(b'RX3 ' + kind.encode())
    save(client, {'players': [player(teams=(('t1', 10), (1, 7)), photo=image(client), generic=False,
                                     face={'source_id': 4242, 'pack': 'colgado', 'name': 'Luis Palma',
                                           'credits': 'Colgado', 'credits_url': 'https://colgado.com'},
                                     boots={'street': 'b1'}, glove=3)]})
    data = export(client, 'players', ['p1'])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        item = json.loads(z.read('manifest.json'))['player']
        assert set(item['face_files']) == {scanface.FILES[k].format(4242) for k in scanface.REQUIRED}
        assert item['boots'] == {'street': 'b1'} and item['glove'] == 3

    import shutil
    shutil.rmtree(face_dir)
    save(client, {})
    _, items = import_all(client, 'players', data)
    pl = items[0]
    assert pl['generic'] is False
    face = {k: pl['face'].get(k) for k in ('source_id', 'pack', 'name', 'credits', 'credits_url')}
    assert face == {'source_id': 4242, 'pack': 'colgado', 'name': 'Luis Palma', 'credits': 'Colgado',
                    'credits_url': 'https://colgado.com'}  # who the face is and who made it go with it
    assert [lk['team'] for lk in pl['teams']] == ['t1', 1]
    for kind in scanface.REQUIRED:
        with open(os.path.join(face_dir, *scanface.FILES[kind].format(4242).split('/')), 'rb') as f:
            assert f.read() == b'RX3 ' + kind.encode()


def test_inspect_changes_nothing_and_apply_takes_only_the_chosen(env):
    client = env['client']
    save(client, {'leagues': [{'uid': 'l1', 'name': 'A', 'image': image(client)}, {'uid': 'l2', 'name': 'B'}]})
    data = export(client, 'leagues', ['l1', 'l2'])
    images = os.path.join(env['state'].store.folder, 'images')
    before = sorted(os.listdir(images))
    r = inspect(client, 'leagues', data)
    assert [i['uid'] for i in r.json()['items']] == ['l1', 'l2']
    assert sorted(os.listdir(images)) == before
    token = r.json()['token']
    r = client.post('/api/share/leagues/apply', json={'token': token, 'uids': ['l2']})
    assert [i['uid'] for i in r.json()['items']] == ['l2']
    # the staged zip is gone once applied
    again = client.post('/api/share/leagues/apply', json={'token': token, 'uids': ['l2']})
    assert again.status_code == 400 and again.json()['detail']['reason'] == 'import_expired'


def test_a_missing_or_broken_file_leaves_the_field_empty(env):
    manifest = {'type': 'fs4-teams', 'version': 1, 'items': [
        {**team(), 'crest': 'nope.png'},
        {**team('t2'), 'crest': 'bad.png'},
        {'uid': '../evil', 'name': 'x'},
        {'uid': 't3', 'name': 'no colors'},
    ]}
    data = make_zip({'manifest.json': json.dumps(manifest), 'bad.png': b'not an image'})
    r = inspect(env['client'], 'teams', data)
    assert r.status_code == 200, r.text
    found = r.json()
    assert [i['uid'] for i in found['items']] == ['t1', 't2']
    assert all(i.get('crest') is None for i in found['items'])
    codes = sorted((p['index'], p['code']) for p in found['problems'])
    assert codes == [(0, 'zip_file_missing'), (1, 'image_invalid'), (2, 'invalid_item'), (3, 'invalid_item')]
    assert all(p['message'] for p in found['problems'])


@pytest.mark.parametrize('files, reason', [
    ({'x.txt': 'x'}, 'no_manifest'),
    ({'manifest.json': '{"type": "fs4-players", "version": 1, "items": []}'}, 'wrong_kind'),
    ({'manifest.json': '{"type": "fs4-boots", "version": 1, "boots": []}'}, 'invalid_manifest'),
    ({'manifest.json': '{"type": "fs4-teams", "version": 99, "items": []}'}, 'zip_too_new'),
    ({'manifest.json': '{}', 'sub/a.png': 'x'}, 'zip_not_flat'),
])
def test_bad_zips_are_refused(env, files, reason):
    r = inspect(env['client'], 'teams', make_zip(files))
    assert r.status_code == 400 and r.json()['detail']['reason'] == reason


def test_export_needs_saved_entries(env):
    r = env['client'].post('/api/share/teams/export', json={'uids': ['nope']})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'share_not_saved'
    assert env['client'].post('/api/share/boots/export', json={'uids': ['x']}).status_code == 422


def test_a_zip_applied_on_an_entry_page_takes_that_entry_uid(env):
    """The zip uploaded on an entry's page fills that entry, which keeps its uid: the face goes into its folder."""
    client, folder = env['client'], env['state'].store.folder
    face_dir = scanface.project_face_dir(folder, 'p1')
    for kind in scanface.REQUIRED:
        path = os.path.join(face_dir, *scanface.FILES[kind].format(77).split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(kind.encode())
    save(client, {'players': [player(generic=False, face={'source_id': 77})]})
    data = export(client, 'players', ['p1'])
    found = inspect(client, 'players', data).json()
    r = client.post('/api/share/players/apply', json={'token': found['token'], 'uids': ['p1'], 'as_uids': {'p1': 'page9'}})
    assert r.status_code == 200, r.text
    assert r.json()['items'][0]['uid'] == 'page9'
    assert os.path.isfile(os.path.join(scanface.project_face_dir(folder, 'page9'),
                                       *scanface.FILES['head'].format(77).split('/')))
    found = inspect(client, 'players', data).json()
    bad = client.post('/api/share/players/apply', json={'token': found['token'], 'uids': ['p1'], 'as_uids': {'p1': '../x'}})
    assert bad.status_code == 400 and bad.json()['detail']['reason'] == 'invalid_target_uid'


def test_several_entries_use_the_plural_layout_and_the_first_one_is_still_read(env):
    client = env['client']
    save(client, {'leagues': [{'uid': 'l1', 'name': 'A'}, {'uid': 'l2', 'name': 'B'}]})
    data = export(client, 'leagues', ['l1', 'l2'])
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(data)).read('manifest.json'))
    assert manifest['type'] == 'fs4-leagues' and [i['uid'] for i in manifest['leagues']] == ['l1', 'l2']
    many = client.post('/api/share/leagues/export', json={'uids': ['l1'], 'many': True})
    assert json.loads(zipfile.ZipFile(io.BytesIO(many.content)).read('manifest.json'))['type'] == 'fs4-leagues'
    # the layout of the first zips (made on the day the feature came, "items") still comes in
    legacy = make_zip({'manifest.json': json.dumps({'type': 'fs4-leagues', 'version': 1,
                                                    'items': [{'uid': 'l9', 'name': 'Old'}]})})
    assert [i['uid'] for i in inspect(client, 'leagues', legacy).json()['items']] == ['l9']
    one_team = make_zip({'manifest.json': json.dumps({'type': 'fs4-team', 'version': 1, 'team': team()})})
    assert inspect(client, 'leagues', one_team).json()['detail']['reason'] == 'wrong_kind'
