"""Real faces from FIFA 14 packs. The pack and the files validated in game are user data outside git: skipped
when missing."""
import io
import os

import pytest
from PIL import Image

from conftest import REPO
from fsmod import facepack, model, preview, rx3mesh, scanface

PACK = os.path.join(REPO, 'Faces', 'various-by-Colgado')  # local face pack (outside git); tests skip without it
VALIDATED = os.path.join(REPO, 'pesquisa', 'faces', 'out', '274254_v14')
FACE = 274254  # validated in game in place of Messi, hair color 3


@pytest.fixture(scope='module')
def assets():
    found = facepack.assets_dir(PACK)
    if not found:
        pytest.skip('face pack not available')
    return found


def test_converter_matches_the_files_validated_in_game(game, assets, monkeypatch):
    """The 274254 reference predates the cap pulled to the scalp (24/10): compared with it off, and the hair with it
    on must be the reference hair pulled."""
    if not os.path.isdir(VALIDATED):
        pytest.skip('validated face not available')
    tpl, src = scanface.template_files(game), facepack.read_face(assets, FACE)
    pulled = scanface.convert(tpl, src, scanface.TEMPLATE, preview.hair_color(3))
    monkeypatch.setattr(scanface, 'CAP_GAP', None)
    out = scanface.convert(tpl, src, scanface.TEMPLATE, preview.hair_color(3))
    hair, head = (scanface.FILES[k].format(scanface.TEMPLATE) for k in ('hair', 'head'))
    assert pulled[hair] == bytes(scanface.cap_to_scalp(bytearray(out[hair]), out[head]))
    assert {n: d for n, d in pulled.items() if n != hair} == {n: d for n, d in out.items() if n != hair}
    expected = {os.path.relpath(os.path.join(root, n), VALIDATED).replace(os.sep, '/')
                for root, _, files in os.walk(VALIDATED) for n in files}
    assert set(out) == expected
    for name, data in out.items():
        with open(os.path.join(VALIDATED, name), 'rb') as f:
            assert data == f.read(), name



def test_scalp_paint_can_be_turned_off(game, assets):
    """paint=False (ScannedFace.paint_scalp) leaves the face texture as converted, only the scalp paint changes."""
    tpl, src = scanface.template_files(game), facepack.read_face(assets, FACE)
    painted = scanface.convert(tpl, src, scanface.TEMPLATE, preview.hair_color(3))
    bare = scanface.convert(tpl, src, scanface.TEMPLATE, preview.hair_color(3), paint=False)
    face = scanface.FILES['face'].format(scanface.TEMPLATE)
    assert painted[face] != bare[face]
    assert {n: d for n, d in painted.items() if n != face} == {n: d for n, d in bare.items() if n != face}
    assert model.ScannedFace(source_id=FACE).paint_scalp is True

def test_pack_folder_with_or_without_screenassets(tmp_path):
    for layout in ('with', 'flat'):
        root = tmp_path / layout / 'my-pack'
        assets = root / 'screenassets' if layout == 'with' else root
        for sub in ('heads', 'faces'):
            (assets / sub).mkdir(parents=True)
        assert facepack.assets_dir(str(root)) == str(assets)  # the pack root
        assert facepack.assets_dir(str(assets)) == str(assets)
        if layout == 'with':
            assert facepack.assets_dir(str(root.parent)) == str(assets)  # a folder with one pack inside
        assert facepack.pack_name(str(assets)) == 'my-pack'
    assert facepack.assets_dir(str(tmp_path)) is None


def test_pack_listing_reads_little_endian_files(assets):
    assert facepack.assets_dir(PACK) == assets  # pack root, with or without screenassets/
    assert facepack.assets_dir(assets) == assets
    assert facepack.pack_name(assets) == os.path.basename(PACK)
    assert facepack.assets_dir(os.path.dirname(PACK)) is None  # Faces/ holds several packs
    faces = facepack.list_faces(assets)  # no count: the pack grows as faces are downloaded
    face = next(f for f in faces if f['id'] == FACE)
    assert face['hair'] and face['hairlod']
    files = facepack.read_face(assets, FACE)
    head = rx3mesh.meshes(files['head'])  # RX3l: 8 influences, u16 bone indices
    assert [m['name'].split('.')[0] for m in head] == ['head', 'eyes']
    assert 148 < min(p[1] for p in head[0]['attrs']['p0']) and max(p[1] for p in head[0]['attrs']['p0']) < 190
    thumb = Image.open(io.BytesIO(facepack.thumbnail(files, size=64)))
    assert thumb.size == (64, 64) and thumb.getpixel((32, 32))[3] == 255  # the face fills the middle


def test_project_face_files_round_trip(assets, tmp_path):
    files = facepack.read_face(assets, FACE)
    folder = scanface.project_face_dir(str(tmp_path), 'jg_01')
    scanface.write_files(folder, FACE, files)
    assert scanface.read_files(folder, FACE) == files
    player = model.Player(uid='jg_01', first_name='A', last_name='B', generic=False,
                          face={'source_id': FACE, 'pack': 'x'})
    assert player.face.source_id == FACE


@pytest.mark.parametrize('face_id, case', [
    (55410, 'hair cap only'), (74651, 'u8 bone indices'), (190456, '1024 face texture'), (276589, 'chunkzip files')])
def test_converter_handles_other_pack_layouts(game, assets, face_id, case):
    from fsmod import rx3tex
    src = facepack.read_face(assets, face_id)
    assert all(d[:4] == b'RX3l' for d in src.values()), case  # compressed files come decoded
    out = scanface.convert(scanface.template_files(game), src, scanface.TEMPLATE, preview.hair_color(3))
    face = out[scanface.FILES['face'].format(scanface.TEMPLATE)]
    assert rx3tex.textures(face)[0]['w'] == 512  # the template's size, whatever the pack had
    bones = {b for m in rx3mesh.meshes(out[scanface.FILES['head'].format(scanface.TEMPLATE)])
             for idx in m['attrs']['i0'] for b in idx}
    assert max(bones) < 252  # FIFA Street skeleton
    hair = out[scanface.FILES['hair'].format(scanface.TEMPLATE)]
    counts = {m['name'].split('.')[0]: len(m['attrs']['p0']) for m in rx3mesh.meshes(hair)}
    if case == 'hair cap only':
        assert min(counts.values()) == 3  # the template's strands are emptied (one zero-area triangle)


def test_build_writes_the_real_face_as_loose_files(game, assets, tmp_path):
    """A non-generic player is built with headclasscode 0 and its face converted for its own new playerid, as loose
    files (validated in game with a playerid that exists nowhere)."""
    from fsmod import builder, chunk, t3db
    from test_builder import PALMEIRAS, load_palmeiras
    import shutil
    project = load_palmeiras()
    shutil.copy(os.path.join(PALMEIRAS, 'escudo_palmeiras.png'), tmp_path)
    pl = project.roster(project.teams[0].uid)[0]
    pl.generic, pl.face = False, model.ScannedFace(source_id=FACE)
    pl.appearance = {**pl.appearance, 'haircolorcode': 3}
    scanface.write_files(scanface.project_face_dir(str(tmp_path), pl.uid), FACE, facepack.read_face(assets, FACE))
    result = builder.build(project, game, str(tmp_path))
    pid = result.assigned_player_ids[pl.uid]
    db = t3db.Database(result.database, game.meta)
    players = db.by_name('players')
    heads = {players.value(r, players.field('playerid')): players.value(r, players.field('headclasscode'))
             for r in players.records}
    assert heads[pid] == 0
    assert heads[result.assigned_player_ids[project.roster(project.teams[0].uid)[1].uid]] == 1
    expected = scanface.convert(scanface.template_files(game), facepack.read_face(assets, FACE), pid,
                                preview.hair_color(3))
    assert {scanface.ASSETS + n for n in expected} <= set(result.loose)
    for name, data in expected.items():
        assert chunk.decode(result.loose[scanface.ASSETS + name]) == data
