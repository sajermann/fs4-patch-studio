"""Balls screen API: original balls, the user's files (kept as sent, fixed names on save), the shared zip, edited game
balls and the ball of each stadium. No pack ball ships with the app, so most tests accept any bytes as a pack file
(the checks and the conversion are tested in core/tests/test_balls.py)."""
import io
import json
import os
import zipfile

import pytest

from fsmod import balls
from test_boots_api import make_zip, png, save


@pytest.fixture
def lenient(env):
    """Any bytes pass as a pack file."""
    env['state'].balls.check = lambda kind, data: None
    return env


def upload(client, kind, data, name):
    if kind == 'thumbnail':
        r = client.post('/api/balls/thumbnail', files={'file': (name, data, 'image/png')})
    else:
        r = client.post(f'/api/balls/files?kind={kind}', files={'file': (name, data, 'application/octet-stream')})
    assert r.status_code == 200, r.text
    return r.json()['path']


def new_ball(client, uid='a1', name='Brazuca'):
    return {'uid': uid, 'name': name, 'credits': 'modder',
            'mesh': upload(client, 'mesh', b'RX3l mesh ' + uid.encode(), 'ball_168.rx3'),
            'texture': upload(client, 'texture', b'RX3l texture ' + uid.encode(), 'ball_168_textures.rx3'),
            'thumbnail': upload(client, 'thumbnail', png(), 'ball 168.png')}


def test_original_balls_and_their_pictures(env):
    client = env['client']
    listed = client.get('/api/originals/balls').json()
    assert [b['id'] for b in listed] == balls.game_ids(env['state'].game)
    by_id = {b['id']: b for b in listed}
    assert by_id[225]['stadiums'] > 10 and by_id[13]['stadiums'] == 0 and by_id[217]['name']
    r = client.get('/api/originals/balls/227.webp')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    assert client.get('/api/originals/balls/240.webp').status_code == 404
    assert client.get('/api/preview/ball/227.glb').status_code == 200
    assert client.get('/api/preview/ball/227.png').content[:4] == b'\x89PNG'
    catalog = client.get('/api/catalog').json()
    assert catalog['balls']['slots'] == 164 and len(catalog['stadium_filters']) == 17


def test_pack_file_is_checked(env):
    client = env['client']
    r = client.post('/api/balls/files?kind=mesh', files={'file': ('x.rx3', b'RX3b not a pack', 'x')})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'ball_mesh_not_pc'
    r = client.post('/api/balls/files?kind=texture', files={'file': ('x.rx3', b'RX3b not a pack', 'x')})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'ball_texture_not_pc'


def test_ball_files_keep_their_bytes_and_get_fixed_names(lenient):
    client, folder = lenient['client'], lenient['tmp'] / 'project'
    ball = new_ball(client)
    sent = (folder / ball['mesh']).read_bytes()
    saved = save(client, {'balls': [ball]})['project']['balls'][0]
    assert saved['mesh'] == 'balls/ball-a1.rx3' and saved['texture'] == 'balls/ball-a1_textures.rx3'
    assert saved['thumbnail'] == 'images/balls/ball-a1.png'
    assert (folder / saved['mesh']).read_bytes() == sent
    assert sorted(os.listdir(folder / 'balls')) == ['ball-a1.rx3', 'ball-a1_textures.rx3']
    save(client, {'balls': []})
    assert os.listdir(folder / 'balls') == []


def test_stadium_balls_are_validated_and_kept(lenient):
    client = lenient['client']
    project = {'balls': [new_ball(client)], 'originals': {'stadium_balls': {'1016': 'a1', '1046': 13, '1047': 999}}}
    body = save(client, project)
    assert body['project']['originals']['stadium_balls'] == {'1016': 'a1', '1046': 13, '1047': 999}
    bad = {(i['code'], i['field']) for i in body['issues'] if i['severity'] == 'error'}
    assert bad == {('stadium_ball_not_found', 'originals.stadium_balls.1047')}


def test_shared_zip_round_trip(lenient):
    client, folder = lenient['client'], lenient['tmp'] / 'project'
    saved = save(client, {'balls': [new_ball(client), new_ball(client, 'a2', 'Jabulani')]})['project']
    r = client.post('/api/balls/export', json={'uids': ['a1']})
    assert r.status_code == 200 and 'ball-Brazuca.zip' in r.headers['content-disposition']
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ['ball-a1.png', 'ball-a1.rx3', 'ball-a1_textures.rx3', 'manifest.json']
    assert json.loads(z.read('manifest.json')) == {'type': 'fs4-ball', 'version': 1, 'ball': {
        'name': 'Brazuca', 'credits': 'modder', 'hidden': False, 'mesh': 'ball-a1.rx3',
        'texture': 'ball-a1_textures.rx3', 'thumbnail': 'ball-a1.png'}}
    assert z.read('ball-a1.rx3') == (folder / saved['balls'][0]['mesh']).read_bytes()
    body = client.post('/api/balls/import', files={'file': ('b.zip', r.content, 'application/zip')}).json()
    assert body['kind'] == 'one' and body['problems'] == []
    back = body['balls'][0]
    assert back['uid'] not in ('a1', 'a2') and back['name'] == 'Brazuca' and back['mesh'] and back['texture']
    many = client.post('/api/balls/export', json={'uids': ['a1', 'a2']})
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(many.content)).read('manifest.json'))
    assert manifest['type'] == 'fs4-balls' and [b['name'] for b in manifest['balls']] == ['Brazuca', 'Jabulani']


def test_bulk_import_keeps_incomplete_balls(lenient):
    client = lenient['client']
    manifest = {'type': 'fs4-balls', 'version': 1, 'balls': [
        {'name': 'Complete', 'mesh': 'a.rx3', 'texture': 'a_t.rx3', 'thumbnail': 'a.png'},
        {'name': 'No texture', 'mesh': 'a.rx3', 'texture': 'gone.rx3'}]}
    body = client.post('/api/balls/import', files={'file': ('b.zip', make_zip(
        {'manifest.json': manifest, 'a.rx3': b'm', 'a_t.rx3': b't', 'a.png': png()}), 'x')}).json()
    assert [b['name'] for b in body['balls']] == ['Complete', 'No texture']
    assert 'texture' not in body['balls'][1]
    assert {(p['index'], p['field'], p['code']) for p in body['problems']} == {(1, 'texture', 'ball_zip_file_missing')}


def test_an_edited_game_ball_is_dropped_when_untouched(lenient):
    client = lenient['client']
    entry = client.post('/api/originals/balls/227/edit?uid=o227').json()
    assert entry == {'uid': 'o227', 'name': 'Original 227', 'credits': 'EA', 'hidden': False, 'original_id': 227}
    assert save(client, {'balls': [entry]})['project'].get('balls', []) == []
    entry['name'] = 'Vermelha'
    assert save(client, {'balls': [entry]})['project']['balls'][0]['name'] == 'Vermelha'
    assert client.post('/api/originals/balls/240/edit?uid=x').status_code == 404


def test_backup_carries_the_ball_files(lenient):
    client = lenient['client']
    save(client, {'balls': [new_ball(client)]})
    z = zipfile.ZipFile(io.BytesIO(client.get('/api/project/backup').content))
    assert {'balls/ball-a1.rx3', 'balls/ball-a1_textures.rx3', 'images/balls/ball-a1.png'} <= set(z.namelist())


PACK = os.environ.get('FSMOD_TEST_BALL_PACK')
PACK_BALL = os.environ.get('FSMOD_TEST_BALL_ID')


@pytest.mark.skipif(not (PACK and PACK_BALL), reason='FSMOD_TEST_BALL_PACK / FSMOD_TEST_BALL_ID not set')
def test_a_pack_ball_from_upload_to_patch(env):
    """A real pack ball: upload, list picture, preview, a stadium using it and the patch's loose files."""
    client = env['client']
    paths = {}
    for kind, name in (('mesh', f'ball_{PACK_BALL}.rx3'), ('texture', f'ball_{PACK_BALL}_textures.rx3')):
        with open(os.path.join(PACK, name), 'rb') as f:
            paths[kind] = upload(client, kind, f.read(), name)
    r = client.get('/api/balls/thumb.webp', params=paths)
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    assert client.get('/api/preview/ball.glb', params=paths).status_code == 200
    assert client.get('/api/preview/ball.png', params=paths).content[:4] == b'\x89PNG'
    body = save(client, {'balls': [{'uid': 'pk', 'name': 'Pack ball', **paths}],
                         'originals': {'stadium_balls': {'1016': 'pk'}}})
    assert not [i for i in body['issues'] if i['severity'] == 'error'], body['issues']
    r = client.post('/api/patch/build')
    assert r.status_code == 200, r.text
    first = balls.free_ids(env['state'].game)[0]
    assert r.json()['assigned_ball_codes'] == {'pk': first}
    files = {f.lower() for f in r.json()['patch']['files']}
    assert {f'game/data/sceneassets/ball/ball_{first}{s}.rx3' for s in ('', '_textures')} <= files
