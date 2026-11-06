"""Goalkeeper gloves (fsmod.gloves): codes, preferred position, validation, the build's glove column, files and
preferred positions, and the conversion of a pack glove.

The pack conversion needs a FIFA 16 PC glove file, which cannot ship with the app: set FSMOD_TEST_GLOVE_PACK to a
folder with gkglove_<id>_textures.rx3 files (FSMOD_TEST_GLOVE_ID picks one; default: the first) to run it.
"""
import glob
import os
import re

import pytest

from fsmod import builder, chunk, gloves, model, original_player, rx3tex, t3db, validation
from fsmod.catalog import Catalog
from test_boots import folder_with_palmeiras
from test_builder import load_palmeiras

GAME_GLOVE = 49  # a glove the game's goalkeepers wear


@pytest.fixture(scope='module')
def catalog(game):
    return Catalog(game)


class FakeConverter:
    """Stands in for gloves.Converter (no pack file here): fixed bytes per file name."""

    def __init__(self):
        self.calls = []

    def files(self, texture, code):
        self.calls.append((texture, code))
        return {name: f'{name}|{len(texture)}'.encode() for name in gloves.file_names(code)}


@pytest.fixture
def folder(tmp_path):
    (tmp_path / 'gloves').mkdir()
    for name in ('a_textures.rx3', 'b_textures.rx3'):
        (tmp_path / 'gloves' / name).write_bytes(b'RX3l' + name.encode())
    return str(tmp_path)


def glove(uid, **kw):
    kw.setdefault('texture', 'gloves/a_textures.rx3')
    return model.Glove(uid=uid, name=uid, **kw)


def link(position, team='t1'):
    return model.TeamLink(team=team, number=1, position=position)


def test_game_codes_and_free_codes(game):
    assert gloves.game_codes(game) == [1, 2, 3, 4, 5, 30, 31, 32, *range(40, 50)]
    free = gloves.free_codes(game)
    assert len(free) == 45 and free[:2] == [6, 7] and free[-1] == 63 and 0 not in free


def test_codes_are_given_and_kept(game):
    project = model.Project(gloves=[glove('a'), glove('b', code=20), glove('dup', code=20), glove('taken', code=30),
                                    glove('edited', original_id=3)])
    out = builder.assign_glove_codes(project, game)
    assert 'b' not in out and 'edited' not in out  # a fitting code stays; an edited game glove has its own
    assert out == {'a': 6, 'dup': 7, 'taken': 8}  # 30 is the game's


def test_codes_run_out(game):
    with pytest.raises(builder.BuildError):
        builder.assign_glove_codes(model.Project(gloves=[glove(f'g{k}') for k in range(46)]), game)


def test_preferred_position():
    pl = model.Player(uid='p', first_name='A', last_name='B')
    assert gloves.preferred_position(pl) == gloves.FALLBACK_POSITION  # no team
    pl.teams = [link(5, 't1'), link(25, 't2'), link(25, 't3')]
    assert gloves.preferred_position(pl) == 25  # most teams
    pl.teams = [link(5, 't1'), link(25, 't2'), link(28, 't3'), link(None, 't4')]
    assert gloves.preferred_position(pl) == 5  # a tie: the first team's; SUB and unknown do not count
    pl.teams = [link(0, 't1'), link(0, 't2'), link(25, 't3')]
    assert gloves.preferred_position(pl) == 0  # goalkeeper in most teams
    pl.teams = [link(25, 't1')]
    pl.glove = 'g1'
    assert gloves.preferred_position(pl) == gloves.GOALKEEPER  # a picked glove wins
    pl.glove = 2
    assert gloves.preferred_position(pl) == gloves.GOALKEEPER


def test_preferred_position_of_an_original_player():
    pl = model.Player(uid='p', first_name='A', last_name='B', original_id=1, teams=[link(8, 't1')])
    assert gloves.preferred_position(pl, 7) == 7  # not a goalkeeper either way: the game's finer choice stays
    assert gloves.preferred_position(pl, 0) == 8  # out of goal: his team position
    pl.glove = 2
    assert gloves.preferred_position(pl, 7) == 0  # a picked glove makes him a goalkeeper
    pl.glove, pl.teams = None, [link(0, 't1')]
    assert gloves.preferred_position(pl, 7) == 0 and gloves.preferred_position(pl, 0) == 0


def test_glove_ref_keeps_its_type():
    assert model.Player.model_validate({'uid': 'p', 'first_name': 'A', 'last_name': 'B', 'glove': 3}).glove == 3
    assert model.Player.model_validate({'uid': 'p', 'first_name': 'A', 'last_name': 'B', 'glove': 'g1'}).glove == 'g1'


def test_validation(game, catalog, folder):
    one, two, three, four = load_palmeiras().players[:4]
    news = [glove(f'n{k}') for k in range(46)]
    hidden, incomplete = glove('hidden', hidden=True), glove('incomplete', texture=None)
    one.glove, two.glove, three.glove, four.glove = 'hidden', 'gone', 7, 3
    project = model.Project(players=[one, two, three, four], gloves=[*news, hidden, incomplete])
    by = {(i.code, i.entity, i.field) for i in validation.validate(project, catalog, folder)}
    assert ('glove_slots_full', 'incomplete', 'hidden') in by and ('glove_slots_full', 'n44', 'hidden') not in by
    assert ('glove_hidden', one.uid, 'glove') in by
    assert ('glove_not_found', two.uid, 'glove') in by
    assert ('glove_not_found', three.uid, 'glove') in by  # 7 is no game glove
    assert ('glove_not_found', four.uid, 'glove') not in by
    assert ('glove_texture_missing', 'incomplete', 'texture') in by
    hidden.texture = None  # a hidden glove takes no code and is not validated
    assert [i.code for i in validation.validate(model.Project(gloves=[hidden]), catalog, folder)] == []


def test_validation_of_edited_game_gloves(catalog, folder):
    opened = model.Glove(uid='g1', name='Original', original_id=GAME_GLOVE)  # opened, file untouched
    unknown = model.Glove(uid='g2', name='Unknown', original_id=10, texture='gloves/a_textures.rx3')
    twice = model.Glove(uid='g3', name='Twice', original_id=GAME_GLOVE)
    missing = model.Glove(uid='g4', name='Missing', original_id=2, texture='gloves/none.rx3')
    issues = {(i.code, i.entity) for i in validation.validate(model.Project(gloves=[opened, unknown, twice, missing]),
                                                              catalog, folder)}
    assert issues == {('original_glove_not_found', 'g2'), ('original_glove_edited_twice', 'g3'),
                      ('glove_file_not_found', 'g4')}


def player_row(db, playerid):
    t = db.by_name('players')
    row = next(r for r in t.records if t.value(r, t.field('playerid')) == playerid)
    return {f: t.value(row, t.field(f)) for f in ('gkglovetypecode', 'preferredposition1')}


def test_build_points_goalkeepers_to_their_gloves(game, folder):
    project = load_palmeiras()
    one, two, three, four = project.players[:4]
    one.glove = 'new'
    two.glove = 2  # a game glove
    three.glove = 'hidden'
    three.appearance = {**three.appearance, 'gkglovetypecode': 44}
    four.glove = None
    four.teams = [lk.model_copy(update={'position': 5}) for lk in four.teams]
    edited = model.Glove(uid='edited', name='Edited 49', original_id=GAME_GLOVE, texture='gloves/b_textures.rx3')
    project.gloves = [glove('new'), glove('unworn'), glove('hidden', hidden=True), edited]
    converter = FakeConverter()
    result = builder.build(project, game, folder_with_palmeiras(folder), glove_converter=converter)
    assert result.assigned_glove_codes == {'new': 6, 'unworn': 7}
    pids = result.assigned_player_ids
    db = t3db.Database(result.database, game.meta)
    assert player_row(db, pids[one.uid]) == {'gkglovetypecode': 6, 'preferredposition1': 0}
    assert player_row(db, pids[two.uid]) == {'gkglovetypecode': 2, 'preferredposition1': 0}
    assert player_row(db, pids[three.uid]) == {'gkglovetypecode': 44, 'preferredposition1': 0}  # keeps his code
    assert player_row(db, pids[four.uid])['preferredposition1'] == 5
    loose = {n for n in result.loose if n.startswith(gloves.GLOVE_DIR)}
    assert loose == set(gloves.file_names(6))  # unworn and hidden gloves: no files
    for name in gloves.file_names(GAME_GLOVE):  # the edited game glove replaces the game's files in data3
        assert result.entries['data3.big', name] == chunk.chunkzip(f'{name}|{len(b"RX3lb_textures.rx3")}'.encode())
    assert sorted(code for _, code in converter.calls) == [6, GAME_GLOVE]


def test_original_player_glove_counts_as_a_change(game, catalog, tmp_path):
    pl = original_player.load(game, catalog, 158023, 'jg_messi', lambda name, data: None)
    pl.photo = None
    pl.loaded.images.pop('photo', None)
    pl.loaded.player.pop('glove', None)  # snapshot taken before gloves existed
    assert not original_player.changes(pl, str(tmp_path)).any
    pl.glove = 2
    assert original_player.changes(pl, str(tmp_path)).fields == {'glove'}


def test_original_player_becomes_goalkeeper(game, catalog, tmp_path):
    pl = original_player.load(game, catalog, 158023, 'jg_messi', lambda name, data: None)
    pl.photo = None
    pl.glove = 2
    project = model.Project(players=[pl])
    result = builder.build(project, game, str(tmp_path), glove_converter=FakeConverter())
    db = t3db.Database(result.database, game.meta)
    assert player_row(db, 158023) == {'gkglovetypecode': 2, 'preferredposition1': 0}


def test_game_gloves_and_thumbnail(game, catalog):
    worn = {g['code']: g['players'] for g in catalog.game_gloves}
    assert set(worn) == set(gloves.game_codes(game)) and worn[1] > 50
    img = gloves.thumbnail(*gloves.game_files(game, 30))
    assert img.width == 256 and img.getbbox() is not None


def test_upload_checks(game):
    _, color = gloves.game_files(game, 2)  # the game's own files are Xbox (RX3b): not a pack's
    with pytest.raises(gloves.GloveError) as e:
        gloves.check_texture(color)
    assert e.value.code == 'glove_texture_not_pc'
    with pytest.raises(gloves.GloveError) as e:
        gloves.check_texture(b'x' * (gloves.MAX_UPLOAD + 1))
    assert e.value.code == 'glove_file_too_big'


PACK = os.environ.get('FSMOD_TEST_GLOVE_PACK')


@pytest.mark.skipif(not PACK, reason='FSMOD_TEST_GLOVE_PACK not set (no pack glove ships with the app)')
def test_pack_glove_conversion(game):
    ids = sorted(int(m.group(1)) for f in glob.glob(os.path.join(PACK, 'gkglove_*_textures.rx3'))
                 if (m := re.search(r'gkglove_(\d+)_textures', f)))
    pick = int(os.environ.get('FSMOD_TEST_GLOVE_ID', ids[0]))
    with open(os.path.join(PACK, f'gkglove_{pick}_textures.rx3'), 'rb') as f:
        texture = f.read()
    files = gloves.Converter(game).files(texture, 6)
    assert list(files) == gloves.file_names(6)
    tpl = gloves.template_files(game)
    color, maps = files.values()
    assert len(color) == len(tpl['color']) and len(maps) == len(tpl['maps'])  # the originals' size (validated)
    assert [t['name'] for t in rx3tex.textures(maps)] == ['gkglove_nm', 'gkglove_coeff']
    coeff = rx3tex.by_name(maps, 'gkglove_coeff')
    assert maps[coeff['off']:coeff['off'] + coeff['size']] == \
        tpl['maps'][coeff['off']:coeff['off'] + coeff['size']]  # the game's coeff map stays
