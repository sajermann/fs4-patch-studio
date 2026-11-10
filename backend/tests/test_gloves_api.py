"""Gloves screen API: original gloves, the user's file (kept as sent, fixed names on save), the shared zip and edited
game gloves. No pack glove ships with the app, so most tests accept any bytes as a pack file (the checks and the
conversion are tested in core/tests/test_gloves.py)."""
import io
import json
import os
import zipfile

import pytest

from fsmod import gloves
from test_boots_api import make_zip, png, save


@pytest.fixture
def lenient(env):
    """Any bytes pass as a pack file."""
    env['state'].gloves.check = lambda data: None
    return env


def upload(client, kind, data, name):
    if kind == 'thumbnail':
        r = client.post('/api/gloves/thumbnail', files={'file': (name, data, 'image/png')})
    else:
        r = client.post('/api/gloves/files', files={'file': (name, data, 'application/octet-stream')})
    assert r.status_code == 200, r.text
    return r.json()['path']


def new_glove(client, uid='g1', name='Predator'):
    return {'uid': uid, 'name': name, 'credits': 'modder',
            'texture': upload(client, 'texture', b'RX3l texture ' + uid.encode(), 'gkglove_149_textures.rx3'),
            'thumbnail': upload(client, 'thumbnail', png(), 'glove 149.png')}


def test_original_gloves_and_their_pictures(env):
    client = env['client']
    listed = client.get('/api/originals/gloves').json()
    assert [g['code'] for g in listed] == gloves.game_codes(env['state'].game)
    assert next(g for g in listed if g['code'] == 1)['players'] > 50
    r = client.get('/api/originals/gloves/30.webp')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    assert client.get('/api/originals/gloves/6.webp').status_code == 404
    assert client.get('/api/catalog').json()['gloves']['slots'] == 45


def test_pack_file_is_checked(env):
    client = env['client']
    r = client.post('/api/gloves/files', files={'file': ('x.rx3', b'RX3b not a pack', 'x')})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'glove_texture_not_pc'
    r = client.post('/api/gloves/thumbnail', files={'file': ('x.gif', png(), 'image/gif')})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'glove_thumbnail_invalid'


def test_glove_files_keep_their_bytes_and_get_fixed_names(lenient):
    client, folder = lenient['client'], lenient['tmp'] / 'project'
    glove = new_glove(client)
    sent = (folder / glove['texture']).read_bytes()
    saved = save(client, {'gloves': [glove]})['project']['gloves'][0]
    assert saved['texture'] == 'gloves/glove-g1_textures.rx3' and saved['thumbnail'] == 'images/gloves/glove-g1.png'
    assert (folder / saved['texture']).read_bytes() == sent  # as the user sent it
    assert os.listdir(folder / 'gloves') == ['glove-g1_textures.rx3']  # the upload renamed
    assert not any(i['entity'] == 'g1' for i in save(client, {'gloves': [saved]})['issues'])
    save(client, {'gloves': []})
    assert os.listdir(folder / 'gloves') == [] and not (folder / 'images' / 'gloves').exists()


def test_slots_are_validated(lenient):
    client = lenient['client']
    many = [{'uid': f'n{k}', 'name': f'N{k}', 'hidden': k == 3, 'texture': 'gloves/x.rx3'} for k in range(47)]
    issues = save(client, {'gloves': many})['issues']
    assert [i['entity'] for i in issues if i['code'] == 'glove_slots_full'] == ['n46']  # the hidden one takes none
    assert 'vagas' in next(i['message'] for i in issues if i['code'] == 'glove_slots_full')


def test_player_glove_is_validated_and_kept(lenient):
    from conftest import palmeiras_v2
    client = lenient['client']
    project, _ = palmeiras_v2(client)
    project['gloves'] = [new_glove(client)]
    project['players'][0]['glove'] = 'g1'
    project['players'][1]['glove'] = 3
    project['players'][2]['glove'] = 7  # no game glove
    body = save(client, project)
    players = body['project']['players']
    assert players[0]['glove'] == 'g1' and players[1]['glove'] == 3
    bad = {(i['code'], i['entity']) for i in body['issues'] if i['code'].startswith('glove')}
    assert bad == {('glove_not_found', players[2]['uid'])}


def test_shared_zip_round_trip(lenient):
    client, folder = lenient['client'], lenient['tmp'] / 'project'
    saved = save(client, {'gloves': [new_glove(client), new_glove(client, 'g2', 'Reusch')]})['project']
    r = client.post('/api/gloves/export', json={'uids': ['g1']})
    assert r.status_code == 200 and 'glove-Predator.zip' in r.headers['content-disposition']
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ['glove-g1.png', 'glove-g1_textures.rx3', 'manifest.json']
    assert json.loads(z.read('manifest.json')) == {'type': 'fs4-glove', 'version': 1, 'glove': {
        'uid': 'g1', 'original_id': None, 'name': 'Predator', 'credits': 'modder', 'hidden': False, 'texture': 'glove-g1_textures.rx3',
        'thumbnail': 'glove-g1.png', 'created_at': saved['gloves'][0]['created_at'],
        'updated_at': saved['gloves'][0]['updated_at']}}
    assert z.read('glove-g1_textures.rx3') == (folder / saved['gloves'][0]['texture']).read_bytes()
    body = client.post('/api/gloves/import', files={'file': ('g.zip', r.content, 'application/zip')}).json()
    assert body['kind'] == 'one' and body['problems'] == []
    back = body['gloves'][0]
    assert back['uid'] == 'g1' and back['name'] == 'Predator'
    assert (folder / back['texture']).read_bytes() == z.read('glove-g1_textures.rx3')
    many = client.post('/api/gloves/export', json={'uids': ['g1', 'g2']})
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(many.content)).read('manifest.json'))
    assert manifest['type'] == 'fs4-gloves' and [g['name'] for g in manifest['gloves']] == ['Predator', 'Reusch']


def test_bulk_import_keeps_incomplete_gloves(lenient):
    client = lenient['client']
    manifest = {'type': 'fs4-gloves', 'version': 1, 'gloves': [
        {'name': 'Complete', 'texture': 'a.rx3', 'thumbnail': 'a.png'},
        {'name': 'No file', 'texture': 'gone.rx3'},
        {'name': 'Bad picture', 'texture': 'a.rx3', 'thumbnail': 'bad.png'}]}
    body = client.post('/api/gloves/import', files={'file': ('g.zip', make_zip(
        {'manifest.json': manifest, 'a.rx3': b't', 'a.png': png(), 'bad.png': b'no'}), 'x')}).json()
    assert [g['name'] for g in body['gloves']] == ['Complete', 'No file', 'Bad picture']
    assert 'texture' not in body['gloves'][1] and 'thumbnail' not in body['gloves'][2]
    assert {(p['index'], p['field'], p['code']) for p in body['problems']} == {
        (1, 'texture', 'glove_zip_file_missing'), (2, 'thumbnail', 'glove_thumbnail_invalid')}


@pytest.mark.parametrize('files,reason', [
    ({'g/manifest.json': {'type': 'fs4-glove', 'version': 1, 'glove': {}}}, 'zip_not_flat'),
    ({'a.rx3': b'x'}, 'no_manifest'),
    ({'manifest.json': {'type': 'fs4-glove', 'version': 2, 'glove': {}}}, 'zip_too_new'),
    ({'manifest.json': {'type': 'fs4-boot', 'version': 1, 'boot': {}}}, 'invalid_manifest'),
])
def test_bad_zips_are_refused(env, files, reason):
    r = env['client'].post('/api/gloves/import', files={'file': ('g.zip', make_zip(files), 'x')})
    assert r.status_code == 400 and r.json()['detail']['reason'] == reason


def test_an_edited_game_glove_is_dropped_when_untouched(lenient):
    client = lenient['client']
    entry = client.post('/api/originals/gloves/49/edit?uid=o49').json()
    assert entry == {'uid': 'o49', 'name': 'Original 49', 'credits': 'EA', 'hidden': False, 'original_id': 49}
    assert save(client, {'gloves': [entry]})['project'].get('gloves', []) == []
    entry['name'] = 'Branca nova'
    assert save(client, {'gloves': [entry]})['project']['gloves'][0]['name'] == 'Branca nova'
    assert client.post('/api/gloves/export', json={'uids': ['o49']}).status_code == 400  # no file of its own
    assert client.post('/api/originals/gloves/6/edit?uid=x').status_code == 404


def test_backup_carries_the_glove_files(lenient):
    client = lenient['client']
    save(client, {'gloves': [new_glove(client)]})
    z = zipfile.ZipFile(io.BytesIO(client.get('/api/project/backup').content))
    assert {'gloves/glove-g1_textures.rx3', 'images/gloves/glove-g1.png'} <= set(z.namelist())


PACK = os.environ.get('FSMOD_TEST_GLOVE_PACK')
PACK_GLOVE = os.environ.get('FSMOD_TEST_GLOVE_ID')


@pytest.mark.skipif(not (PACK and PACK_GLOVE), reason='FSMOD_TEST_GLOVE_PACK / FSMOD_TEST_GLOVE_ID not set')
def test_a_pack_glove_from_upload_to_patch(env):
    """A real pack glove: upload, list picture, preview texture, a goalkeeper wearing it and the patch's loose files."""
    from conftest import palmeiras_v2
    client = env['client']
    name = f'gkglove_{PACK_GLOVE}_textures.rx3'
    with open(os.path.join(PACK, name), 'rb') as f:
        texture = upload(client, 'texture', f.read(), name)
    r = client.get('/api/gloves/thumb.webp', params={'texture': texture})
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    assert client.get('/api/preview/glove.png', params={'texture': texture}).content[:4] == b'\x89PNG'
    project, _ = palmeiras_v2(client)
    project['gloves'] = [{'uid': 'pk', 'name': 'Pack glove', 'texture': texture}]
    project['players'][0]['glove'] = 'pk'
    body = save(client, project)
    assert not [i for i in body['issues'] if i['severity'] == 'error'], body['issues']
    r = client.post('/api/patch/build')
    assert r.status_code == 200, r.text
    assert r.json()['assigned_glove_codes'] == {'pk': 6}
    assert client.get('/api/project').json()['project']['gloves'][0]['code'] == 6
    files = {f.lower() for f in r.json()['patch']['files']}
    assert {f'game/data/sceneassets/gkglove/gkglove_0_6_{s}.rx3' for s in ('cm', 'textures')} <= files
