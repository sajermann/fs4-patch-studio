"""Menu fonts (Patches screen): the user's .ttf is checked, kept as sent under fonts/ with a fixed name on save, shown
in a preview and validated (the conversion itself is tested in core/tests/test_uifonts.py). The game's courier font
stands for the user's file."""
import io
import os

from PIL import Image

from fsmod import uifonts
from test_boots_api import save


def user_font(env):
    return uifonts.original(env['state'].game, 'courier')


def upload(client, data, name='MyFont-Bold.ttf'):
    return client.post('/api/ui-fonts/files', files={'file': (name, data, 'font/ttf')})


def test_upload_checks_the_font(env):
    client = env['client']
    r = upload(client, b'OTTO' + bytes(64), 'cff.otf')
    assert r.status_code == 400 and r.json()['detail']['code'] == 'ui_font_not_truetype'
    r = upload(client, b'hello')
    assert r.status_code == 400 and r.json()['detail']['code'] == 'ui_font_unreadable'
    r = upload(client, user_font(env))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['path'].startswith('fonts/upload-') and body['path'].endswith('.ttf')
    assert body['name'] == 'FS4 Courier Medium' and body['missing_chars'] == ''


def test_font_is_kept_as_sent_and_gets_its_slot_name(env):
    client, folder = env['client'], env['tmp'] / 'project'
    data = user_font(env)
    path = upload(client, data).json()['path']
    saved = save(client, {'game_patches': {'ui_fonts': {'cn_bold': {'file': path, 'name': 'FS4 Courier Medium'}}}})
    choice = saved['project']['game_patches']['ui_fonts']['cn_bold']
    assert choice == {'file': 'fonts/ui-font-cn_bold.ttf', 'name': 'FS4 Courier Medium'}
    assert (folder / choice['file']).read_bytes() == data
    assert os.listdir(folder / 'fonts') == ['ui-font-cn_bold.ttf']
    assert not [i for i in saved['issues'] if (i['field'] or '').startswith('game_patches')]
    save(client, {'game_patches': {'ui_fonts': {}}})
    assert os.listdir(folder / 'fonts') == []


def test_preview_of_the_game_font_and_of_the_users(env):
    client = env['client']
    plain = client.get('/api/ui-fonts/cn_bold/preview.png')
    assert plain.status_code == 200 and plain.headers['content-type'] == 'image/png'
    path = upload(client, user_font(env)).json()['path']
    mine = client.get('/api/ui-fonts/cn_bold/preview.png', params={'file': path})
    assert mine.status_code == 200 and mine.content != plain.content
    assert Image.open(io.BytesIO(mine.content)).size[1] == Image.open(io.BytesIO(plain.content)).size[1]
    assert client.get('/api/ui-fonts/cn_bold/preview.png', params={'file': 'fonts/gone.ttf'}).status_code == 404
    assert client.get('/api/ui-fonts/arial/preview.png').status_code == 422


def test_missing_file_is_an_error(env):
    issues = save(env['client'], {'game_patches': {'ui_fonts': {'header': {'file': 'fonts/gone.ttf'}}}})['issues']
    issue = next(i for i in issues if i['code'] == 'ui_font_file_not_found')
    assert issue['severity'] == 'error' and issue['field'] == 'game_patches.ui_fonts.header'
    assert 'header' in issue['message']


def test_install_then_uninstall_brings_the_game_fonts_back(env):
    """A menu font goes into the game as a loose file plus data0.bh; uninstalling puts the original data0.bh back
    and removes the loose font, so the game reads its own font from data0.big again."""
    client, tmp = env['client'], env['tmp']
    path = upload(client, user_font(env)).json()['path']
    save(client, {'game_patches': {'ui_fonts': {'cn_bold': {'file': path, 'name': 'FS4 Courier Medium'}}}})
    r = client.post('/api/patch/build')
    assert r.status_code == 200, r.text
    files = {f.lower() for f in r.json()['patch']['files']}
    assert {'game/data/ui/fonts/fs4_cn_bold.ttf', 'game/data0.bh'} < files
    game = tmp / 'game' / 'Game'
    patched_bh = tmp / 'patch' / 'Game' / 'data0.bh'
    assert client.post('/api/patch/install').status_code == 200
    font = game / 'data' / 'ui' / 'fonts' / 'fs4_cn_bold.ttf'
    assert font.exists() and (game / 'data0.bh').read_bytes() == patched_bh.read_bytes()

    r = client.post('/api/patch/uninstall')
    assert r.status_code == 200, r.text
    assert not font.exists() and not (game / 'data' / 'ui' / 'fonts').exists()
    with open(os.path.join(env['state'].game.folder, 'Game', 'data0.bh'), 'rb') as f:
        assert (game / 'data0.bh').read_bytes() == f.read()  # the game's own index: the font is found in data0.big


def test_reinstall_without_the_font_brings_the_game_font_back(env):
    """Taking the font out of the project and installing again also restores the game's font."""
    client, tmp = env['client'], env['tmp']
    path = upload(client, user_font(env)).json()['path']
    save(client, {'game_patches': {'ui_fonts': {'cn_bold': {'file': path}}}})
    assert client.post('/api/patch/build').status_code == 200
    assert client.post('/api/patch/install').status_code == 200
    font = tmp / 'game' / 'Game' / 'data' / 'ui' / 'fonts' / 'fs4_cn_bold.ttf'
    assert font.exists()
    save(client, {'game_patches': {'ui_fonts': {}}})
    assert client.post('/api/patch/build').status_code == 200
    r = client.post('/api/patch/install')
    assert r.status_code == 200, r.text
    assert not font.exists()
    with open(os.path.join(env['state'].game.folder, 'Game', 'data0.bh'), 'rb') as f:
        assert (tmp / 'game' / 'Game' / 'data0.bh').read_bytes() == f.read()
