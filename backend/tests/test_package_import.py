"""FIFA patch packages (fsmod.fifapackage): a package made by an external extractor, with the source game's values,
converted for this game and imported through the shared zip path."""
import io
import json
import zipfile

from PIL import Image

from test_share_api import inspect, make_zip, png


def _player(pid, first, last, overall, position, team, number, **extra):
    return {
        'source_id': pid, 'names': {'first': first, 'last': last, 'jersey': last}, 'birthdate': '1990-05-04',
        'birthdate_suspect': False, 'height': 300, 'weight': 75, 'preferred_foot': 'left',
        'positions': [{'code': position, 'name': 'X'}], 'nationality_id': 34,
        'attributes': {'overall': overall, 'acceleration': 80, 'sprint_speed': 90, 'skill_moves': 3, 'finishing': 70},
        'appearance': {'headtypecode': 99999, 'skintonecode': 3},
        'photo': None, 'face': None,
        'teams': [{'team_id': team, 'jersey_number': number, 'position': 28 if number > 11 else position}],
        'raw': {'players': [{'playerid': pid}]}, **extra}


def package(manifest_extra=None, players=None):
    """A small package: one league, one team with a kit, a crest and fonts, three players (one with a face)."""
    files = {'leagues/10/logo.png': png(), 'teams/20/crest.png': png(), 'teams/20/crest-no-background.png': png(),
             'teams/20/kits/0/jersey.png': png(), 'teams/20/kits/0/shorts.png': png(),
             'game/data/sceneassets/kitnumbers/kitnumbers_1_3.rx3': b'not a font', 'players/30/photo.png': png(),
             'game/data/sceneassets/heads/head_30_0.rx3': b'head',
             'game/data/sceneassets/faces/face_30_0_0_0_0_0_0_0_0_textures.rx3': b'face'}
    manifest = {
        'format': 'fifa-patch-package', 'format_version': 1,
        'source': {'game': 'fifa14', 'platform': 'pc', 'patch_name': 'My patch'},
        'credits': {'text': 'Someone', 'url': 'someone.example'},
        'leagues': [{'source_id': 10, 'names': {'database': 'Some League (1)', 'full': 'Some Very Long League Name',
                                                'abbr15': 'Some League'},
                     'images': {'logo': {'image': 'leagues/10/logo.png'}}, 'raw': {}}],
        'teams': [{'source_id': 20, 'names': {'database': 'Ünïon Team 1960-65', 'abbr3': 'UNT', 'abbr15': 'Union'},
                   'colors': {'primary': [1, 2, 3], 'secondary': [4, 5, 6]}, 'league_ids': [10, 99],
                   'crest': {'image': 'teams/20/crest.png', 'image_no_background': 'teams/20/crest-no-background.png',
                             'preferred': 'no_background'},
                   'kits': [{'type': 0, 'role': 'home', 'jersey': 'teams/20/kits/0/jersey.png',
                             'shorts': 'teams/20/kits/0/shorts.png', 'collar': 15, 'name_color': [9, 9, 9],
                             'front_number_placement': 1, 'shorts_number_placement': 0, 'back_name_placement': 0,
                             'number_font': {'id': 1, 'color': 3, 'ink_color': [250, 250, 250],
                                             'file': 'game/data/sceneassets/kitnumbers/kitnumbers_1_3.rx3'},
                             'shorts_number_font': {'id': 1, 'color': 4}, 'name_font': {'id': 2},
                             'print_positions': None},
                            {'type': 3, 'role': None, 'jersey': 'x', 'shorts': 'y'}],
                   'roster': [{'player_id': 30}, {'player_id': 31}, {'player_id': 32}],
                   'captain_id': 999, 'takers': {'penalty': 31, 'free_kick': 999}, 'raw': {}}],
        'players': players or [
            _player(30, 'Jürgen', 'Æsir', 70, 25, 20, 9, photo={'image': 'players/30/photo.png'},
                    face={'files': {'data/sceneassets/heads/head_30_0.rx3': {'kind': 'head', 'file':
                                    'game/data/sceneassets/heads/head_30_0.rx3'},
                                    'data/sceneassets/faces/face_30_0_0_0_0_0_0_0_0_textures.rx3': {
                                        'kind': 'face',
                                        'file': 'game/data/sceneassets/faces/face_30_0_0_0_0_0_0_0_0_textures.rx3'}}}),
            _player(31, 'Big', 'Keeper', 80, 0, 20, 1, birthdate_suspect=True),
            _player(32, 'Sub', 'Player', 60, 14, 20, 19),
        ],
        'nations': [{'source_id': 34, 'name': 'Holland', 'national_team_id': None}],
        **(manifest_extra or {}),
    }
    return make_zip({'package.json': json.dumps(manifest), **files})


def inspect_package(client, data, prefix=None):
    return client.post('/api/share/package/inspect', files={'file': ('p.fifapkg.zip', data, 'application/zip')},
                       data={'prefix': prefix} if prefix is not None else None)


def test_package_is_converted_for_this_game(env):
    client = env['client']
    r = inspect_package(client, package())
    assert r.status_code == 200, r.text
    found = r.json()
    assert found['summary']['patch_name'] == 'My patch'
    assert found['summary']['counts'] == {'leagues': 1, 'teams': 1, 'players': 3}
    kinds = found['kinds']
    league = kinds['leagues']['items'][0]
    assert league['uid'] == 'fifa14-l10' and league['short_name'] == 'Some League'
    assert league['image'] == 'league-fifa14-l10.png'
    team = kinds['teams']['items'][0]
    assert team['uid'] == 'fifa14-t20' and team['leagues'] == ['fifa14-l10']  # a league not in the package: left out
    assert team['short_name'] == 'Union' and team['abbreviation'] == 'UNT'
    assert team['captain'] == 'fifa14-p31'  # the package's captain is not in the roster: the best overall
    assert team['takers'] == {'penalty': 'fifa14-p31'}
    assert team['kit_credits'] == 'Someone' and team['kit_credits_url'] == 'https://someone.example'
    home = team['real_kits']['home']
    assert set(team['real_kits']) == {'home'}  # a kit without a role is not a slot here
    assert home['collar'] == 0 and home['front_number'] is True and home['show_name'] is False
    assert home['number_color'] == 1  # the ink of the font file is white, whatever the palette index said
    players = {p['uid']: p for p in kinds['players']['items']}
    star = players['fifa14-p30']
    assert star['height'] == 277 and star['foot'] == 'left'
    assert star['skills']['TRI'] == 4 and star['skills']['overall'] == 70
    assert star['appearance']['headtypecode'] != 99999  # the nearest code this game has
    assert star['fields']['nationality'] is not None  # by name ("Holland")
    assert star['face'] and star['face']['credits'] == 'Someone' and star['generic'] is False
    keeper = players['fifa14-p31']
    assert keeper.get('birthdate') is None and keeper['skills']['SPE'] >= 45
    assert players['fifa14-p32']['teams'] == [{'team': 'fifa14-t20', 'number': 19, 'position': 14}]


def test_package_import_puts_files_in_the_project(env):
    client = env['client']
    kinds = inspect_package(client, package(), prefix='mine-').json()['kinds']
    applied = {}
    for kind in ('leagues', 'teams', 'players'):
        part = kinds[kind]
        r = client.post(f'/api/share/{kind}/apply', json={'token': part['token'],
                                                          'uids': [i['uid'] for i in part['items']]})
        assert r.status_code == 200, r.text
        applied[kind] = r.json()['items']
    assert applied['teams'][0]['uid'] == 'mine-t20'
    assert applied['teams'][0]['crest'].startswith('images/')
    star = next(p for p in applied['players'] if p['uid'] == 'mine-p30')
    assert star['photo'] and star['face']['source_id'] == 30


def test_package_errors(env):
    client = env['client']
    r = inspect(client, 'teams', package())
    assert r.json()['detail']['reason'] == 'use_package_import'
    r = inspect_package(client, package({'format_version': 99}))
    assert r.json()['detail']['reason'] == 'package_too_new'
    r = inspect_package(client, make_zip({'manifest.json': '{}'}))
    assert r.json()['detail']['reason'] == 'not_a_package'
    r = inspect_package(client, package(), prefix='bad prefix!')
    assert r.json()['detail']['reason'] == 'invalid_prefix'
    buf = io.BytesIO()
    Image.new('RGB', (2, 2)).save(buf, format='PNG')
    r = inspect_package(client, buf.getvalue())
    assert r.json()['detail']['reason'] == 'not_a_zip'
    with zipfile.ZipFile(io.BytesIO(package())) as z:
        assert 'package.json' in z.namelist()
