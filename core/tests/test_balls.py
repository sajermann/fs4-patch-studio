"""Balls (fsmod.balls) and stadiums: ids, the catalog's stadiums, validation, the build's stadium balls and files, and
the conversion of a pack ball.

The pack conversion needs FIFA 16 PC ball files, which cannot ship with the app: set FSMOD_TEST_BALL_PACK to a folder
with ball_<id>.rx3 + ball_<id>_textures.rx3 files (FSMOD_TEST_BALL_ID picks one; default: the first) to run it.
"""
import glob
import os
import re

import pytest

from fsmod import balls, builder, chunk, model, rx3mesh, rx3tex, t3db, validation
from fsmod.catalog import Catalog

GAME_BALL = 227  # a ball the game's stadiums use (Paris)
UNUSED_GAME_BALL = 13  # a FIFA 12 leftover no stadium uses (works in game)
UNDERPASS_2 = [1016, 1017, 1018, 1019, 1020, 1021, 1304]  # its country versions
PARIS = 1046


@pytest.fixture(scope='module')
def catalog(game):
    return Catalog(game)


class FakeConverter:
    """Stands in for balls.Converter (no pack file here): fixed bytes per file name."""

    def __init__(self):
        self.calls = []

    def files(self, mesh, texture, ball_id):
        self.calls.append(ball_id)
        return {name: f'{name}|{len(mesh)}|{len(texture)}'.encode() for name in balls.file_names(ball_id)}


@pytest.fixture
def folder(tmp_path):
    (tmp_path / 'balls').mkdir()
    for name in ('a.rx3', 'a_textures.rx3', 'b.rx3', 'b_textures.rx3'):
        (tmp_path / 'balls' / name).write_bytes(b'RX3l' + name.encode())
    return str(tmp_path)


def ball(uid, **kw):
    kw.setdefault('mesh', 'balls/a.rx3')
    kw.setdefault('texture', 'balls/a_textures.rx3')
    return model.Ball(uid=uid, name=uid, **kw)


def test_game_ids_and_free_ids(game):
    ids = balls.game_ids(game)
    assert len(ids) == 91 and {225, 231, 246, 13, 222} <= set(ids) and 0 not in ids
    free = balls.free_ids(game)
    assert len(free) == 164 and 240 in free and 255 in free and not set(free) & set(ids)


def test_triangles_of_a_strip():
    assert balls.triangles([0, 1, 2, 3]) == [0, 1, 2, 2, 1, 3]  # every other one turned back
    assert balls.triangles([0, 1, 2, 2, 3, 3, 4, 5, 6]) == [0, 1, 2, 4, 3, 5, 4, 5, 6]  # degenerate joins dropped


def test_ids_are_given_and_kept(game):
    project = model.Project(balls=[ball('a'), ball('b', code=240), ball('dup', code=240), ball('taken', code=231),
                                   ball('edited', original_id=GAME_BALL)])
    out = builder.assign_ball_codes(project, game)
    assert 'b' not in out and 'edited' not in out  # a fitting id stays; an edited game ball has its own
    free = balls.free_ids(game)
    assert out == {'a': free[0], 'dup': free[1], 'taken': free[2]}  # 231 is the game's


def test_catalog_stadiums(catalog):
    every = catalog.all_stadiums
    assert len(every) == 42 and sum(len(s['versions']) for s in every) == 120
    by_name = {}
    for s in every:
        by_name.setdefault(s['name'], []).append(s)
    underpass = by_name['Underpass 2'][0]
    assert [v['id'] for v in underpass['versions']] == UNDERPASS_2
    assert [v['region'] for v in underpass['versions']] == [1, 2, 3, 4, 5, 6, 7]
    assert underpass['versions'][0]['ball'] == 231 and underpass['lockable_id'] is None
    assert 11 in underpass['filters'] and 0 not in underpass['filters']  # 5-a-side, not futsal
    paris = by_name['Paris: Notre Dame'][0]
    assert paris['lockable_id'] == PARIS and paris['locked'] and paris['versions'] == [
        {'id': PARIS, 'region': -1, 'ball': GAME_BALL, 'menu': True}]
    assert by_name['London'][0]['times'] == [1, 4] and by_name['Goals Centre'][0]['times'] in ([1, 3], [1])
    assert len(by_name['Goals Centre']) == 2  # two different stadiums with one name
    assert {s['name'] for s in every if 0 in s['filters']} == {
        'Futsal Centre', 'Berlin Stadium', 'Plaça de Catalunya', 'Tokyo Futsal Stadium', 'Rio Stadium', 'The Hangar'}
    assert sum(1 for s in every if s['lockable_id'] is not None) == 22
    names = {b['id']: b['name'] for b in catalog.game_balls}
    assert names[217] == 'Astore Pro Grace Catalunya' and names[GAME_BALL] is None


def test_menus_list_the_flagged_rows(catalog):
    """The stadiums of each menu, as seen in game, and the version an ordinary match loaded."""
    def menu(setup):
        return sorted(s['name'] for s in catalog.all_stadiums if s['in_menu'] and setup in s['filters'])
    assert menu(11) == sorted(['Underpass 2', 'Goals Centre', 'The Dome', 'London', 'Paris: Notre Dame', 'Venice Canal',
                               'Justin Chan Memorial', 'Indoor Court', 'New York Stadium', 'Dubai', 'adidas Z5',
                               'Barcelona Stadium', 'Amsterdam Stadium'])
    assert len(menu(0)) == 6 and len(menu(2)) == 7
    assert menu(16) == sorted(['Basketball Court', 'Shanghai Rooftop mini goal', 'Aberdeen Cage'])
    loaded = {v['id'] for s in catalog.all_stadiums for v in s['versions'] if v['menu']}
    assert {1017, 1023, 1041, 1032, 1036} <= loaded  # England, England, England, Germany, France
    for s in catalog.all_stadiums:
        assert sum(v['menu'] for v in s['versions']) == (1 if s['name'] not in ('Underpass 1', 'adidas Z5 - Freeroam') else 0)


def test_validation(catalog, folder):
    news = [ball(f'n{k}') for k in range(165)]
    hidden, incomplete = ball('hidden', hidden=True), ball('incomplete', texture=None)
    opened = model.Ball(uid='o1', name='Original', original_id=GAME_BALL)  # files untouched
    half = model.Ball(uid='o2', name='Half', original_id=231, mesh='balls/b.rx3')
    unknown = model.Ball(uid='o3', name='Unknown', original_id=240)
    twice = model.Ball(uid='o4', name='Twice', original_id=GAME_BALL)
    originals = model.OriginalChanges(stadium_balls={PARIS: 'hidden', 1016: 'gone', 1017: 999, 9999: GAME_BALL,
                                                     1018: UNUSED_GAME_BALL, 1019: 'n0'})
    project = model.Project(balls=[*news, hidden, incomplete, opened, half, unknown, twice], originals=originals)
    by = {(i.code, i.entity, i.field) for i in validation.validate(project, catalog, folder)}
    assert ('ball_slots_full', 'n164', 'hidden') in by and ('ball_slots_full', 'n163', 'hidden') not in by
    assert ('ball_files_missing', 'incomplete', 'texture') in by
    assert ('ball_files_missing', 'o2', 'texture') in by and ('ball_files_missing', 'o1', 'mesh') not in by
    assert ('original_ball_not_found', 'o3', 'original_id') in by
    assert ('original_ball_edited_twice', 'o4', 'original_id') in by
    assert ('stadium_ball_hidden', 'hidden', 'hidden') in by
    assert ('stadium_ball_not_found', None, 'originals.stadium_balls.1016') in by
    assert ('stadium_ball_not_found', None, 'originals.stadium_balls.1017') in by
    assert ('stadium_not_found', None, 'originals.stadium_balls.9999') in by
    assert not {x for x in by if x[2] in ('originals.stadium_balls.1018', 'originals.stadium_balls.1019')}


def stadium_balls(db):
    t = db.by_name('stadiums')
    return {t.value(r, t.field('stadiumid')): t.value(r, t.field('balltype')) for r in t.records}


def test_build_gives_stadiums_their_balls(game, folder):
    edited = model.Ball(uid='edited', name='Edited 227', original_id=GAME_BALL, mesh='balls/b.rx3',
                        texture='balls/b_textures.rx3')
    project = model.Project(balls=[ball('new'), ball('unused'), ball('hidden', hidden=True), edited])
    project.originals.stadium_balls = {**{sid: 'new' for sid in UNDERPASS_2}, 1022: UNUSED_GAME_BALL,
                                       1040: 'hidden'}
    converter = FakeConverter()
    result = builder.build(project, game, folder, ball_converter=converter)
    free = balls.free_ids(game)
    assert result.assigned_ball_codes == {'new': free[0], 'unused': free[1]}
    got = stadium_balls(t3db.Database(result.database, game.meta))
    assert all(got[sid] == free[0] for sid in UNDERPASS_2)
    assert got[1022] == UNUSED_GAME_BALL
    assert got[1040] == 226 and got[PARIS] == GAME_BALL  # hidden ball: the game's stays; untouched stadium
    loose = {n for n in result.loose if n.startswith(balls.BALL_DIR)}
    assert loose == set(balls.file_names(free[0]))  # unused and hidden balls: no files
    for name in balls.file_names(GAME_BALL):  # the edited game ball replaces the game's files in data3
        assert result.entries['data3.big', name] == chunk.chunkzip(f'{name}|{len(b"RX3lb.rx3")}|{len(b"RX3lb_textures.rx3")}'.encode())
    assert sorted(converter.calls) == sorted([free[0], GAME_BALL])


def test_game_ball_thumbnail_and_preview(game):
    mesh, textures = balls.game_files(game, GAME_BALL)
    img = balls.thumbnail(mesh, textures)
    assert img.size == (256, 256) and img.getbbox() is not None
    m = balls.glb_mesh(mesh)
    assert len(m['indices']) % 3 == 0 and max(m['indices']) < len(m['positions'])


def test_upload_checks(game):
    mesh, textures = balls.game_files(game, GAME_BALL)  # the game's own files are Xbox (RX3b): not a pack's
    with pytest.raises(balls.BallError) as e:
        balls.check_mesh(mesh)
    assert e.value.code == 'ball_mesh_not_pc'
    with pytest.raises(balls.BallError) as e:
        balls.check_texture(textures)
    assert e.value.code == 'ball_texture_not_pc'
    with pytest.raises(balls.BallError) as e:
        balls.check_mesh(b'x' * (balls.MAX_UPLOAD + 1))
    assert e.value.code == 'ball_file_too_big'


PACK = os.environ.get('FSMOD_TEST_BALL_PACK')


@pytest.mark.skipif(not PACK, reason='FSMOD_TEST_BALL_PACK not set (no pack ball ships with the app)')
def test_pack_ball_conversion(game):
    ids = sorted(int(m.group(1)) for f in glob.glob(os.path.join(PACK, 'ball_*_textures.rx3'))
                 if (m := re.search(r'ball_(\d+)_textures', f)))
    pick = int(os.environ.get('FSMOD_TEST_BALL_ID', ids[0]))
    data = []
    for name in (f'ball_{pick}.rx3', f'ball_{pick}_textures.rx3'):
        with open(os.path.join(PACK, name), 'rb') as f:
            data.append(f.read())
    files = balls.Converter(game).files(*data, 240)
    assert list(files) == balls.file_names(240)
    mesh, textures = files.values()
    assert mesh[:4] == b'RX3b' and textures[:4] == b'RX3b'
    m = rx3mesh.meshes(mesh)[0]
    assert m['name'].startswith('ball_240') or 'ball_240' in m['name']
    assert [t['name'] for t in rx3tex.textures(textures)][:2] == ['ball_cm', 'ball_nm']
    assert balls.thumbnail(mesh, textures).getbbox() is not None
