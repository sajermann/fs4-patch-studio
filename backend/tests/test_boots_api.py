"""Boots screen API: original boots, the user's files (kept as sent, fixed names on save), the shared zip and edited
game boots. No pack boot ships with the app, so most tests accept any bytes as a pack file (the checks and the
conversion are tested in core/tests/test_boots.py)."""
import io
import json
import os
import zipfile

import pytest
from PIL import Image

from fsmod import boots


@pytest.fixture
def lenient(env):
    """Any bytes pass as a pack file and the boot pictures are drawn from a stand-in."""
    service = env['state'].boots
    service.check = lambda kind, data: None
    service.converted = lambda mesh, texture: (_ for _ in ()).throw(boots.BootError('boot_mesh_invalid'))
    return env


def png(color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new('RGB', (64, 32), color).save(buf, format='PNG')
    return buf.getvalue()


def upload(client, kind, data, name):
    if kind == 'thumbnail':
        r = client.post('/api/boots/thumbnail', files={'file': (name, data, 'image/png')})
    else:
        r = client.post(f'/api/boots/files?kind={kind}', files={'file': (name, data, 'application/octet-stream')})
    assert r.status_code == 200, r.text
    return r.json()['path']


def new_boot(client, uid='b1', name='Mercurial', street=True):
    return {'uid': uid, 'name': name, 'credits': 'modder', 'street': street,
            'mesh': upload(client, 'mesh', b'RX3l mesh ' + uid.encode(), 'shoe_1466.rx3'),
            'texture': upload(client, 'texture', b'RX3l texture ' + uid.encode(), 'shoe_1466_0_textures.rx3'),
            'thumbnail': upload(client, 'thumbnail', png(), 'shoe 1466.png')}


def save(client, project):
    r = client.put('/api/project', json=project)
    assert r.status_code == 200, r.text
    return r.json()


def test_original_boots_and_their_pictures(env):
    client = env['client']
    listed = client.get('/api/originals/boots').json()
    assert len(listed) == 186
    by_code = {b['code']: b for b in listed}
    assert by_code[611]['street'] and by_code[611]['players'] > 200 and not by_code[50]['street']
    r = client.get('/api/originals/boots/611.webp')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    assert client.get('/api/originals/boots/150.webp').status_code == 404
    assert client.get('/api/catalog').json()['boots']['street_slots'] == 39


def test_pack_files_are_checked(env):
    client = env['client']
    r = client.post('/api/boots/files?kind=mesh', files={'file': ('x.rx3', b'RX3b not a pack', 'x')})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'boot_mesh_not_pc'
    r = client.post('/api/boots/thumbnail', files={'file': ('x.gif', png(), 'image/gif')})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'boot_thumbnail_invalid'


def test_boot_files_keep_their_bytes_and_get_fixed_names(lenient):
    client, folder = lenient['client'], lenient['tmp'] / 'project'
    boot = new_boot(client)
    sent = (folder / boot['mesh']).read_bytes()
    saved = save(client, {'boots': [boot]})['project']['boots'][0]
    assert saved['mesh'] == 'boots/boot-b1.rx3' and saved['texture'] == 'boots/boot-b1_textures.rx3'
    assert saved['thumbnail'] == 'images/boots/boot-b1.png'
    assert (folder / saved['mesh']).read_bytes() == sent  # as the user sent it
    assert sorted(os.listdir(folder / 'boots')) == ['boot-b1.rx3', 'boot-b1_textures.rx3']  # uploads renamed
    issues = {(i['code'], i['entity']) for i in save(client, {'boots': [saved]})['issues']}
    assert not any(e == 'b1' for _, e in issues)
    save(client, {'boots': []})
    assert os.listdir(folder / 'boots') == [] and not (folder / 'images' / 'boots').exists()


def test_street_slots_are_validated(lenient):
    client = lenient['client']
    street = [{'uid': f's{k}', 'name': f'S{k}', 'street': True, 'hidden': k == 39,
               'mesh': 'boots/x.rx3', 'texture': 'boots/x_textures.rx3'} for k in range(41)]
    issues = save(client, {'boots': street})['issues']
    full = [i['entity'] for i in issues if i['code'] == 'boot_street_full']
    assert full == ['s40']  # the hidden one takes no street code
    assert 'vagas' in next(i['message'] for i in issues if i['code'] == 'boot_street_full')


def test_shared_zip_round_trip(lenient):
    client, folder = lenient['client'], lenient['tmp'] / 'project'
    saved = save(client, {'boots': [new_boot(client), new_boot(client, 'b2', 'Predator', False)]})['project']
    r = client.post('/api/boots/export', json={'uids': ['b1']})
    assert r.status_code == 200 and 'boot-Mercurial.zip' in r.headers['content-disposition']
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ['boot-b1.png', 'boot-b1.rx3', 'boot-b1_textures.rx3', 'manifest.json']
    manifest = json.loads(z.read('manifest.json'))
    assert manifest == {'type': 'fs4-boot', 'version': 1, 'boot': {
        'name': 'Mercurial', 'credits': 'modder', 'street': True, 'hidden': False, 'mesh': 'boot-b1.rx3',
        'texture': 'boot-b1_textures.rx3', 'thumbnail': 'boot-b1.png'}}
    assert z.read('boot-b1.rx3') == (folder / saved['boots'][0]['mesh']).read_bytes()
    r = client.post('/api/boots/import', files={'file': ('b.zip', r.content, 'application/zip')})
    body = r.json()
    assert r.status_code == 200 and body['kind'] == 'one' and body['problems'] == []
    back = body['boots'][0]
    assert back['uid'] not in ('b1', 'b2') and back['name'] == 'Mercurial' and back['street'] is True
    assert (folder / back['mesh']).read_bytes() == z.read('boot-b1.rx3')  # a provisional upload, not saved yet
    many = client.post('/api/boots/export', json={'uids': ['b1', 'b2']})
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(many.content)).read('manifest.json'))
    assert manifest['type'] == 'fs4-boots' and [b['name'] for b in manifest['boots']] == ['Mercurial', 'Predator']


def test_downloaded_manifest_lists_empty_fields(lenient):
    client = lenient['client']
    boot = {**new_boot(client), 'credits': None, 'thumbnail': None}
    save(client, {'boots': [boot]})
    r = client.post('/api/boots/export', json={'uids': ['b1']})
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert json.loads(z.read('manifest.json'))['boot'] == {
        'name': 'Mercurial', 'credits': None, 'street': True, 'hidden': False, 'mesh': 'boot-b1.rx3',
        'texture': 'boot-b1_textures.rx3', 'thumbnail': None}
    # filled in by hand: the picture added to the zip and named in the manifest
    files = {n: z.read(n) for n in z.namelist() if n != 'manifest.json'}
    manifest = json.loads(z.read('manifest.json'))
    manifest['boot'].update(credits='modder', thumbnail='mercurial.png')
    body = client.post('/api/boots/import', files={'file': (
        'b.zip', make_zip({**files, 'mercurial.png': png(), 'manifest.json': manifest}), 'application/zip')}).json()
    back = body['boots'][0]
    assert body['problems'] == [] and back['credits'] == 'modder' and back['thumbnail']


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, bytes) else json.dumps(data))
    return buf.getvalue()


def test_bulk_import_keeps_incomplete_boots(lenient):
    client = lenient['client']
    manifest = {'type': 'fs4-boots', 'version': 1, 'boots': [
        {'name': 'Complete', 'mesh': 'a.rx3', 'texture': 'a_t.rx3', 'thumbnail': 'a.png', 'street': True},
        {'name': 'No texture', 'mesh': 'a.rx3', 'texture': 'gone.rx3', 'hidden': True},
        {'name': 'Bad picture', 'mesh': 'a.rx3', 'texture': 'a_t.rx3', 'thumbnail': 'bad.png'}]}
    r = client.post('/api/boots/import', files={'file': ('b.zip', make_zip(
        {'manifest.json': manifest, 'a.rx3': b'm', 'a_t.rx3': b't', 'a.png': png(), 'bad.png': b'no'}), 'x')})
    body = r.json()
    assert body['kind'] == 'many' and [b['name'] for b in body['boots']] == ['Complete', 'No texture', 'Bad picture']
    assert 'texture' not in body['boots'][1] and body['boots'][1]['hidden'] is True
    assert 'thumbnail' not in body['boots'][2]
    assert {(p['index'], p['field'], p['code']) for p in body['problems']} == {
        (1, 'texture', 'boot_zip_file_missing'), (2, 'thumbnail', 'boot_thumbnail_invalid')}
    assert body['boots'][0]['mesh'] == body['boots'][1]['mesh']  # one stored copy of a shared file


@pytest.mark.parametrize('files,reason', [
    ({'boots/manifest.json': {'type': 'fs4-boot', 'version': 1, 'boot': {}}}, 'zip_not_flat'),
    ({'a.rx3': b'x'}, 'no_manifest'),
    ({'manifest.json': {'type': 'fs4-boot', 'version': 2, 'boot': {}}}, 'zip_too_new'),
    ({'manifest.json': {'type': 'fs4-kit', 'version': 1}}, 'invalid_manifest'),
])
def test_bad_zips_are_refused(env, files, reason):
    r = env['client'].post('/api/boots/import', files={'file': ('b.zip', make_zip(files), 'x')})
    assert r.status_code == 400 and r.json()['detail']['reason'] == reason


def test_an_edited_game_boot_is_dropped_when_untouched(lenient):
    client = lenient['client']
    entry = client.post('/api/originals/boots/611/edit?uid=g611').json()
    assert entry == {'uid': 'g611', 'name': 'Original 611', 'credits': 'EA', 'street': False, 'hidden': False,
                     'original_id': 611}
    assert save(client, {'boots': [entry]})['project'].get('boots', []) == []
    entry['name'] = 'Mercurial no lugar da 611'
    assert save(client, {'boots': [entry]})['project']['boots'][0]['name'] == 'Mercurial no lugar da 611'
    r = client.post('/api/boots/export', json={'uids': ['g611']})
    assert r.status_code == 400  # no files of its own: nothing to share
    assert client.post('/api/originals/boots/150/edit?uid=x').status_code == 404


def test_backup_carries_the_boot_files(lenient):
    client = lenient['client']
    save(client, {'boots': [new_boot(client)]})
    z = zipfile.ZipFile(io.BytesIO(client.get('/api/project/backup').content))
    assert {'boots/boot-b1.rx3', 'boots/boot-b1_textures.rx3', 'images/boots/boot-b1.png'} <= set(z.namelist())


PACK = os.environ.get('FSMOD_TEST_BOOT_PACK')
PACK_BOOT = os.environ.get('FSMOD_TEST_BOOT_ID')


@pytest.mark.skipif(not (PACK and PACK_BOOT), reason='FSMOD_TEST_BOOT_PACK / FSMOD_TEST_BOOT_ID not set')
def test_a_pack_boot_from_upload_to_patch(env):
    """A real pack boot: upload, list picture, 3D preview, a player wearing it and the patch's loose files."""
    from conftest import palmeiras_v2
    client = env['client']
    paths = {}
    for kind, name in (('mesh', f'shoe_{PACK_BOOT}.rx3'), ('texture', f'shoe_{PACK_BOOT}_0_textures.rx3')):
        with open(os.path.join(PACK, name), 'rb') as f:
            paths[kind] = upload(client, kind, f.read(), name)
    r = client.get('/api/boots/thumb.webp', params=paths)
    assert r.status_code == 200 and r.headers['content-type'] == 'image/webp'
    r = client.get('/api/preview/boot.glb', params=paths)
    assert r.status_code == 200 and r.content[:4] == b'glTF'
    assert client.get('/api/preview/boot.png', params=paths).content[:4] == b'\x89PNG'
    project, _ = palmeiras_v2(client)
    project['boots'] = [{'uid': 'pk', 'name': 'Pack boot', 'street': True, **paths}]
    project['players'][0]['boots'] = {'street': 'pk', 'turf': 'pk', 'indoor': 'pk'}
    body = save(client, project)
    assert not [i for i in body['issues'] if i['severity'] == 'error'], body['issues']
    r = client.post('/api/patch/build')
    assert r.status_code == 200, r.text
    assert r.json()['assigned_boot_codes'] == {'pk': 561}
    assert client.get('/api/project').json()['project']['boots'][0]['code'] == 561
    files = {f.lower() for f in r.json()['patch']['files']}
    assert {f'game/data/sceneassets/shoe/shoe_561{s}.rx3' for s in ('', '_0_textures', '_textures')} <= files
