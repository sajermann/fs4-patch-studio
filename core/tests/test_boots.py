"""Boots (fsmod.boots): codes, validation, the build's boot columns and files, and the conversion of a pack boot.

The pack conversion needs a FIFA 14-16 PC boot pair, which cannot ship with the app: set FSMOD_TEST_BOOT_PACK to a
folder with shoe_<id>.rx3 + shoe_<id>_0_textures.rx3 files (FSMOD_TEST_BOOT_ID picks one; default: the first) to
run it.
"""
import glob
import os
import re

import numpy as np
import pytest

from fsmod import boots, builder, chunk, model, original_player, rx3mesh, t3db, validation
from fsmod.catalog import Catalog
from test_builder import PALMEIRAS, load_palmeiras

GAME_BOOT = 611  # the game's most worn boot


@pytest.fixture(scope='module')
def catalog(game):
    return Catalog(game)


class FakeConverter:
    """Stands in for boots.Converter (no pack files here): fixed bytes per file name."""

    def __init__(self):
        self.calls = []

    def files(self, mesh, texture, code):
        self.calls.append((mesh, texture, code))
        return {name: f'{name}|{len(mesh)}|{len(texture)}'.encode() for name in boots.file_names(code)}


@pytest.fixture
def folder(tmp_path):
    (tmp_path / 'boots').mkdir()
    for name in ('a.rx3', 'a_textures.rx3', 'b.rx3', 'b_textures.rx3'):
        (tmp_path / 'boots' / name).write_bytes(b'RX3l' + name.encode())
    return str(tmp_path)


def boot(uid, street=False, **kw):
    kw.setdefault('mesh', 'boots/a.rx3')
    kw.setdefault('texture', 'boots/a_textures.rx3')
    return model.Boot(uid=uid, name=uid, street=street, **kw)


def codes_of(issues):
    return [i.code for i in issues]


def test_game_codes_and_free_codes(game):
    codes = boots.game_codes(game)
    assert len(codes) == 186 and GAME_BOOT in codes and 223 in codes
    assert boots.free_street_codes(game) == list(range(561, 600))
    assert len(boots.free_new_codes(game)) == 404 and boots.free_new_codes(game)[0] == 620


def test_codes_are_given_and_kept(game):
    project = model.Project(boots=[boot('s1', True), boot('n1'), boot('s2', True, code=570), boot('n2', code=700),
                                   boot('dup', code=700), boot('wrong', True, code=650)])
    out = builder.assign_boot_codes(project, game)
    assert 's2' not in out and 'n2' not in out  # fitting codes stay
    assert out['s1'] == 561 and out['wrong'] == 562  # a street boot needs a street code
    assert out['n1'] == 620 and out['dup'] == 621  # the second boot with code 700 gets another one


def test_street_codes_run_out(game):
    project = model.Project(boots=[boot(f's{k}', True) for k in range(40)])
    with pytest.raises(builder.BuildError):
        builder.assign_boot_codes(project, game)


def test_validation(game, catalog, folder):
    pl = load_palmeiras().players[0]
    street = [boot(f's{k}', True) for k in range(40)]
    ok, hidden, incomplete = boot('ok'), boot('hidden', hidden=True), boot('incomplete', mesh=None)
    pl.boots = {'street': 'ok', 'turf': 'hidden', 'indoor': 'gone'}
    project = model.Project(players=[pl], boots=[*street, ok, hidden, incomplete])
    issues = validation.validate(project, catalog, folder)
    by = {(i.code, i.entity, i.field) for i in issues}
    assert ('boot_street_full', 's39', 'street') in by and ('boot_street_full', 's38', 'street') not in by
    assert ('boot_not_street', pl.uid, 'boots.street') in by
    assert ('boot_hidden', pl.uid, 'boots.turf') in by
    assert ('boot_not_found', pl.uid, 'boots.indoor') in by
    assert ('boot_mesh_missing', 'incomplete', 'mesh') in by
    hidden.street = True  # a hidden boot takes no street code and is not validated
    assert codes_of(validation.validate(model.Project(boots=[hidden]), catalog, folder)) == []


def test_validation_of_edited_game_boots(game, catalog, folder):
    opened = model.Boot(uid='g1', name='Original', original_id=GAME_BOOT)  # opened, files untouched
    half = model.Boot(uid='g2', name='Half', original_id=600, mesh='boots/a.rx3')
    unknown = model.Boot(uid='g3', name='Unknown', original_id=150, mesh='boots/a.rx3', texture='boots/a_textures.rx3')
    twice = model.Boot(uid='g4', name='Twice', original_id=GAME_BOOT)
    issues = {(i.code, i.entity) for i in validation.validate(model.Project(boots=[opened, half, unknown, twice]),
                                                              catalog, folder)}
    assert issues == {('boot_texture_missing', 'g2'), ('original_boot_not_found', 'g3'),
                      ('original_boot_edited_twice', 'g4')}


def player_row(db, playerid):
    t = db.by_name('players')
    row = next(r for r in t.records if t.value(r, t.field('playerid')) == playerid)
    return {f: t.value(row, t.field(f)) for f in boots.SURFACE_FIELDS.values()}


def test_build_points_players_to_their_boots(game, folder):
    project = load_palmeiras()
    one, two, three = project.players[:3]
    one.boots = {'street': 'street', 'turf': 'other', 'indoor': 'other'}
    two.appearance = {**two.appearance, 'shoetypecode': 605}  # only the street boot: the same everywhere
    three.boots = {'turf': 'hidden'}
    three.appearance = {**three.appearance, 'shoetypecode': 604, 'turf_shoe': 508, 'indoor_shoe': 501}
    edited = model.Boot(uid='edited', name='Edited 611', original_id=GAME_BOOT, mesh='boots/b.rx3',
                        texture='boots/b_textures.rx3')
    project.boots = [boot('street', True), boot('other', mesh='boots/b.rx3', texture='boots/b_textures.rx3'),
                     boot('unworn'), boot('hidden', hidden=True), edited]
    converter = FakeConverter()
    result = builder.build(project, game, folder_with_palmeiras(folder), boot_converter=converter)
    assert result.assigned_boot_codes == {'street': 561, 'other': 620, 'unworn': 621}
    pids = result.assigned_player_ids
    db = t3db.Database(result.database, game.meta)
    assert player_row(db, pids[one.uid]) == {'shoetypecode': 561, 'turf_shoe': 620, 'indoor_shoe': 620}
    assert player_row(db, pids[two.uid]) == {'shoetypecode': 605, 'turf_shoe': 605, 'indoor_shoe': 605}
    assert player_row(db, pids[three.uid]) == {'shoetypecode': 604, 'turf_shoe': 508, 'indoor_shoe': 501}
    loose = {n for n in result.loose if n.startswith(boots.SHOE_DIR)}
    assert loose == set(boots.file_names(561) + boots.file_names(620))  # unworn and hidden boots: no files
    for name in boots.file_names(GAME_BOOT):  # the edited game boot replaces the game's files in their archive
        assert result.entries['data3.big', name] == chunk.chunkzip(f'{name}|{len(b"RX3lb.rx3")}|'
                                                                   f'{len(b"RX3lb_textures.rx3")}'.encode())
    assert sorted(code for *_, code in converter.calls) == [561, GAME_BOOT, 620]


def folder_with_palmeiras(folder):
    """The Palmeiras fixture's images copied next to the boot files of `folder`."""
    import shutil
    for entry in os.listdir(PALMEIRAS):
        src = os.path.join(PALMEIRAS, entry)
        dst = os.path.join(folder, entry)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)
        elif os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy(src, dst)
    return folder


def test_original_player_boots_count_as_a_change(game, catalog, tmp_path):
    pl = original_player.load(game, catalog, 158023, 'jg_messi', lambda name, data: None)
    pl.photo = None
    pl.loaded.images.pop('photo', None)
    pl.loaded.player.pop('boots')  # snapshot taken before boots existed
    assert not original_player.changes(pl, str(tmp_path)).any
    pl.boots = {'street': 'b1'}
    assert original_player.changes(pl, str(tmp_path)).fields == {'boots'}


def test_appearance_options_of_boots(catalog):
    options = catalog.appearance_options
    assert options['shoetypecode'] == [c for c in boots.game_codes(catalog.game) if 500 <= c <= 619]
    assert options['turf_shoe'] == options['indoor_shoe'] == boots.game_codes(catalog.game)
    worn = {b['code']: b for b in catalog.game_boots}
    assert worn[GAME_BOOT]['players'] > 200 and worn[GAME_BOOT]['street'] and not worn[50]['street']


def test_upload_checks(game):
    mesh, color = boots.game_files(game, GAME_BOOT)  # the game's own files are Xbox (RX3b): not a pack's
    with pytest.raises(boots.BootError) as e:
        boots.check_mesh(mesh)
    assert e.value.code == 'boot_mesh_not_pc'
    with pytest.raises(boots.BootError) as e:
        boots.check_texture(b'not an rx3')
    assert e.value.code == 'boot_texture_not_pc'
    img = boots.thumbnail(mesh, color)
    assert img.width == 256 and img.getbbox() is not None


PACK = os.environ.get('FSMOD_TEST_BOOT_PACK')


@pytest.mark.skipif(not PACK, reason='FSMOD_TEST_BOOT_PACK not set (no pack boot ships with the app)')
def test_pack_boot_conversion(game):
    ids = sorted(int(m.group(1)) for f in glob.glob(os.path.join(PACK, 'shoe_*_0_textures.rx3'))
                 if (m := re.search(r'shoe_(\d+)_0_textures', f)))
    pick = int(os.environ.get('FSMOD_TEST_BOOT_ID', ids[0]))
    with open(os.path.join(PACK, f'shoe_{pick}.rx3'), 'rb') as f:
        mesh = f.read()
    with open(os.path.join(PACK, f'shoe_{pick}_0_textures.rx3'), 'rb') as f:
        texture = f.read()
    files = boots.Converter(game).files(mesh, texture, 561)
    assert list(files) == boots.file_names(561)
    m = rx3mesh.meshes(files[boots.file_names(561)[0]])[0]
    used = {i for v, w in zip(m['attrs']['i0'], m['attrs']['w0']) for i, x in zip(v, w) if x}
    assert used <= {0, 4, 5, 6, 31, 32, 33}  # the game's leg bones only
    assert rx3mesh.names(files[boots.file_names(561)[0]]) == ['shoe_561shoe_.FxRenderableSimple']
    # the outer shell ends up outside the sock (laces may still touch it)
    tri, norms = boots.template_files(game)['sock']
    p = np.array(m['attrs']['p0'])[:, :3]
    n = np.array(m['attrs']['n0'])
    bottom = tri[:, :, 1].min() + boots.MARGIN
    close = 0
    for i in np.where(p[:, 1] > bottom)[0]:
        d, q, normal = boots.signed_distance(p[i], tri, norms)
        if q[1] >= bottom and float(n[i] @ normal) >= 0 and d < boots.GAP - 0.05:
            close += 1
    assert close < 0.15 * len(p)
