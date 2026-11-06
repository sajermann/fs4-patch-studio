"""Real faces from FIFA 14 packs. The pack and the files validated in game are user data outside git: skipped
when missing."""
import io
import os

import pytest
from PIL import Image

from conftest import REPO
from fsmod import facepack, model, preview, rx3mesh, rx3tex, scanface

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
    on must be the reference hair pulled. It also predates the fit of the back of the neck, the paint skipping the eyes and
    the hair color map resized apart from its alpha: off here too."""
    if not os.path.isdir(VALIDATED):
        pytest.skip('validated face not available')
    monkeypatch.setattr(scanface, 'NAPE_FRONT', -1e9)
    monkeypatch.setattr(scanface, 'PAINT_SKIPS_EYES', False)
    monkeypatch.setattr(scanface, 'HAIR_FOLLOWS_SKIN', False)
    monkeypatch.setattr(rx3tex, 'DXT5_RESIZE_APART', False)
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


def test_converter_takes_ids_of_any_length(game, assets):
    """An original player with a 4-digit playerid (Henry, 1625; validated in game): the name sections of head, face
    and eyes are byte for byte the game's own files of that player, and the hair still parses."""
    henry = 1625
    out = scanface.convert(scanface.template_files(game), facepack.read_face(assets, FACE), henry, preview.hair_color(1))
    assert set(out) == {f.format(henry) for f in scanface.FILES.values()}
    own = scanface.game_files(game, henry)
    for kind in ('head', 'face', 'eyes'):
        mine, theirs = (scanface.of_type(d, '>', scanface.NAMES)[0] for d in (out[scanface.FILES[kind].format(henry)],
                                                                               own[kind]))
        assert out[scanface.FILES[kind].format(henry)][mine[0]:sum(mine)] == own[kind][theirs[0]:sum(theirs)], kind
    hair = out[scanface.FILES['hair'].format(henry)]
    assert scanface.hair_parts(hair) == {'strands': 0, 'cap': 1} and b'hair_1625_0_0player' in hair



def test_scalp_paint_can_be_turned_off(game, assets):
    """paint=False (ScannedFace.paint_scalp) leaves the face texture as converted, only the scalp paint changes."""
    tpl, src = scanface.template_files(game), facepack.read_face(assets, FACE)
    painted = scanface.convert(tpl, src, scanface.TEMPLATE, preview.hair_color(3))
    bare = scanface.convert(tpl, src, scanface.TEMPLATE, preview.hair_color(3), paint=False)
    face = scanface.FILES['face'].format(scanface.TEMPLATE)
    assert painted[face] != bare[face]
    assert {n: d for n, d in painted.items() if n != face} == {n: d for n, d in bare.items() if n != face}
    assert model.ScannedFace(source_id=FACE).paint_scalp is True

def test_face_in_an_unknown_format_is_reported(game):
    """Whatever breaks inside the converter reaches the app as FaceFormatError (the build and the preview handle it)."""
    tpl = scanface.template_files(game)
    with pytest.raises(scanface.FaceFormatError):
        scanface.convert(tpl, {'head': b'RX3l' + bytes(60), 'face': b'RX3l' + bytes(60)}, scanface.TEMPLATE, '#000000')
    with pytest.raises(scanface.FaceFormatError, match='missing face files'):
        scanface.convert(tpl, {}, scanface.TEMPLATE, '#000000')


@pytest.mark.parametrize('pack, face_id, case', [
    ('redo-facepack-132-by-redo1000', 200779, 'no teeth where they are expected'),
    ('redo-facepack-133-by-redo1000', 241861, 'lower teeth on the head bone'),
    ('redo-facepack-126-by-redo1000', 72421, 'garbage after a wrong small mip'),
    ('redo-facepack-140-by-redo1000', 999131, 'hair with strands only')])
def test_converter_handles_odd_faces(game, pack, face_id, case):
    assets = facepack.assets_dir(os.path.join(REPO, 'Faces', pack))
    if not assets:
        pytest.skip('face pack not available')
    src = facepack.read_face(assets, face_id)
    out = scanface.convert(scanface.template_files(game), src, scanface.TEMPLATE, preview.hair_color(1), paint=False,
                           hair_mode='volume')
    hair = out[scanface.FILES['hair'].format(scanface.TEMPLATE)]
    assert scanface.hair_parts(hair) == {'strands': 0, 'cap': 1}, case


def test_head_with_swapped_meshes_is_not_converted(game):
    assets = facepack.assets_dir(os.path.join(REPO, 'Faces', 'redo-facepack-130-by-redo1000'))
    if not assets:
        pytest.skip('face pack not available')
    with pytest.raises(scanface.FaceFormatError, match='swapped'):
        scanface.convert(scanface.template_files(game), facepack.read_face(assets, 999099), scanface.TEMPLATE, '#000000')


def _pack_face(*path, face_id):
    assets = facepack.assets_dir(os.path.join(REPO, 'Faces', *path))
    if not assets:
        pytest.skip('face pack not available')
    return facepack.read_face(assets, face_id)


def _hair_weight(hair, bone):
    """Share of the hair's bone weight on one bone, over all its meshes."""
    total = on_bone = 0
    for k in range(len(scanface.of_type(hair, '>', scanface.VERTICES))):
        for _, weights in scanface.vertex_bones(hair, '>', k, scanface.decl(hair, '>', k)):
            total += sum(weights.values())
            on_bone += weights.get(bone, 0)
    return on_bone / total


def test_head_stored_eyes_first_has_the_usual_order_after_the_fix(game):
    """Names right, eyes stored first: the same two meshes, each with its own bytes."""
    head = _pack_face('pele-by-classic-patch', 'base', face_id=190043)['head']
    fixed = scanface.head_mesh_first(head)
    before, after = rx3mesh.meshes(head), rx3mesh.meshes(fixed)
    assert [m['name'].split('.')[0] for m in before] == ['eyes_', 'head_']
    assert [m['name'].split('.')[0] for m in after] == ['head_', 'eyes_']
    assert before[0]['attrs'] == after[1]['attrs'] and before[0]['indices'] == after[1]['indices']
    assert before[1]['attrs'] == after[0]['attrs'] and before[1]['indices'] == after[0]['indices']
    assert scanface.head_mesh_first(fixed) == fixed


@pytest.mark.parametrize('face_id, case', [
    (215107, 'eyes stored first, meshes named eyes/head without the underscore'),
    (215108, 'hair texture whose 2x2/1x1 mips have another pitch')])
def test_converter_handles_other_tools(game, face_id, case):
    files = _pack_face('some-faces-from-jgarca', face_id=face_id)
    out = scanface.convert(scanface.template_files(game), files, scanface.TEMPLATE, '#000000', paint=False)
    head = rx3mesh.meshes(out[scanface.FILES['head'].format(scanface.TEMPLATE)])
    assert len(head[0]['attrs']['p0']) > len(head[1]['attrs']['p0']), case


def test_head_stored_eyes_first_is_converted(game):
    files = _pack_face('pele-by-classic-patch', 'base', face_id=190043)
    out = scanface.convert(scanface.template_files(game), files, scanface.TEMPLATE, '#000000', paint=False)
    assert scanface.FILES['head'].format(scanface.TEMPLATE) in out


def test_hair_stays_on_the_head_when_the_nearest_bone_is_the_jaw(game):
    """The hair of this face moved with the mouth: its head bone landed on the template's jaw."""
    files = _pack_face('neymar_pack_by_ViP3eR', '2014_wc', face_id=190871)
    template = scanface.template_files(game)
    hair = scanface.convert(template, files, scanface.TEMPLATE, '#000000', paint=False)[
        scanface.FILES['hair'].format(scanface.TEMPLATE)]
    head_bone = scanface.head_bone(template['head'], '>')
    jaw = scanface.jaw_family(scanface.vertex_bones(template['head'], '>', 0, scanface.decl(template['head'], '>', 0)),
                              head_bone)[0]
    assert _hair_weight(hair, head_bone) > 0.9
    assert _hair_weight(hair, jaw) < 0.01


def test_only_the_beard_follows_the_jaw(game):
    """Same vote, different places: hair above the eyes stays on the head, a beard below them goes with the chin."""
    template = scanface.template_files(game)
    top = scanface.head_bone(template['head'], '>')

    def jaw_bones(*path, face_id):
        files = _pack_face(*path, face_id=face_id)
        head = scanface.head_mesh_first(files['head'])
        follow = scanface.skin_follow(template['head'], head, scanface.align_offset(template['head'], head))
        guarded = scanface.beard_only_on_jaw(follow, files['hair'], template['head'], head)
        return {b for b, t in follow.items() if t != top}, {b for b, t in guarded.items() if t != top}

    voted, kept = jaw_bones('redo-facepack-125-by-redo1000', face_id=237685)
    assert voted - kept, 'hair above the eyes must leave the jaw'
    voted, kept = jaw_bones('various-by-Colgado', face_id=243614)
    assert 23 in voted and 23 in kept, 'the beard must stay on the jaw'


def test_hair_color_map_keeps_its_color_with_a_low_alpha(game):
    """The alpha of hair_cm is not opacity: a resize that premultiplies it wrecks the color."""
    tex = bytearray(scanface.template_files(game)['hair_textures'])
    t = rx3tex.by_name(tex, 'hair_cm')
    rx3tex.set_image(tex, t, Image.new('RGBA', (t['w'] * 2, t['h'] * 2), (120, 90, 60, 8)))
    r, g, b, a = rx3tex.to_image(tex, t).getpixel((5, 5))
    assert abs(r - 120) < 8 and abs(g - 90) < 8 and abs(b - 60) < 8 and abs(a - 8) < 8


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


@pytest.fixture(scope='module')
def rig_pack():
    """Pack whose faces hang the eyes on a bone outside the skin; some of them bring hair with another rig's matrices."""
    found = facepack.assets_dir(os.path.join(REPO, 'Faces', 'some-faces-from-jgarca'))
    if not found:
        pytest.skip('face pack not available')
    return found


@pytest.mark.parametrize('face_id', [142708, 204485, 209331, 212188, 216816])
def test_converter_handles_eyes_on_a_bone_outside_the_skin(game, rig_pack, face_id):
    src = facepack.read_face(rig_pack, face_id)
    skin = {b for _, bw in scanface.vertex_bones(src['head'], '<', 0, scanface.decl(src['head'], '<', 0)) for b in bw}
    assert not skin & scanface.used_bones(src['head'], '<', 1, scanface.decl(src['head'], '<', 1))
    assert scanface.head_bone(src['head'], '<') in skin
    out = scanface.convert(scanface.template_files(game), src, scanface.TEMPLATE, preview.hair_color(1))
    assert set(out) == {f.format(scanface.TEMPLATE) for f in scanface.FILES.values()}


def test_hair_with_another_rigs_matrices_uses_the_heads_skeleton(rig_pack, assets):
    src = facepack.read_face(rig_pack, 204485)
    assert scanface.hair_skeleton(src['hair'], src['head']) == scanface.bone_positions(src['head'], '<')
    ok = facepack.read_face(assets, FACE)
    assert scanface.hair_skeleton(ok['hair'], ok['head']) == scanface.bone_positions(ok['hair'], '<')


def test_lash_strip_below_the_eye_is_raised(game, rig_pack):
    """Mo Salah's strip crosses the eye in the pack; one already above the middle stays where it is."""
    tpl = scanface.template_files(game)
    out = scanface.convert(tpl, facepack.read_face(rig_pack, 209331), scanface.TEMPLATE, preview.hair_color(1))
    hair, head = (out[scanface.FILES[k].format(scanface.TEMPLATE)] for k in ('hair', 'head'))
    assert scanface.raise_lashes(hair, head) == hair  # now in place: nothing left to raise
    eye = [m for m in rx3mesh.meshes(head) if 'eyes' in m['name']][0]['attrs']['p0']
    cap = [m for m in rx3mesh.meshes(hair) if 'alphaA' in m['name']][0]['attrs']
    lash = [p[1] for p, uv in zip(cap['p0'], cap['t0']) if 0.03 <= uv[0] <= 0.04 and 0.06 <= uv[1] <= 0.11]
    assert lash and sum(lash) / len(lash) > (min(p[1] for p in eye) + max(p[1] for p in eye)) / 2


def test_back_of_the_neck_follows_the_template(game):
    """Only behind the neck and only inwards: the fit never widens it nor touches the front or the head; the weights
    fade into the template's there and the rest keeps the voted ones."""
    tpl = scanface.template_files(game)['head']
    fit = scanface.neck_fitter(tpl, 0)
    assert fit((0.0, 165.0, 9.0)) == (0.0, 165.0, 9.0)  # in front, above the chin
    assert fit((0.0, 170.0, -9.0)) == (0.0, 170.0, -9.0)  # above the nape
    assert fit((0.0, 164.0, -12.0))[2] > -12.0  # too wide: pulled in
    assert fit((0.0, 165.5, -3.0))[2] == -3.0  # slimmer than the template: stays
    weights = scanface.neck_weights(tpl, 0, scanface.decl(tpl, '>', 0))
    normal = (0.0, 0.0, -1.0)
    voted = ([147, 0, 0, 0], [255, 0, 0, 0])
    assert weights((0.0, 170.0, -7.0), normal, *voted) is None
    assert weights((0.0, 165.0, 9.0), (0.0, 0.0, 1.0), *voted) is None
    idx, scaled = weights((0.0, 164.0, -7.0), normal, *voted)
    assert sum(scaled) == 255 and len(idx) == 4 and set(idx) - {147, 0}  # the template's bones came in


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


def test_hair_color_suggested_from_the_face():
    """The player's hair color (used by the scalp paint) is suggested from the face's own hair."""
    codes = range(len(preview.HAIR_COLORS))
    assert preview.nearest_hair_color((0, 0, 0), codes) == 1  # black
    assert preview.nearest_hair_color((79, 59, 41), codes) == 6  # neutral brown, not the reddish one (7)
    assert scanface.hair_rgb({}) is None  # bald: no suggestion
    files = _pack_face('some-faces-from-jgarca', face_id=215108)  # textures named hair_coeff.dds / hair_cm.dds
    assert preview.nearest_hair_color(scanface.hair_rgb(files), codes) == 6
