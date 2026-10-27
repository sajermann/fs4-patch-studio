import io
import json
import struct

from PIL import Image

from fsmod import catalog, preview


def glb_nodes(glb):
    assert glb[:4] == b'glTF' and struct.unpack('<I', glb[8:12])[0] == len(glb)
    length = struct.unpack('<I', glb[12:16])[0]
    doc = json.loads(glb[20:20 + length])
    return {n['name']: doc['accessors'][doc['meshes'][n['mesh']]['primitives'][0]['attributes']['POSITION']]
            for n in doc['nodes']}


def test_every_generic_head_and_hair_converts(game):
    options = catalog.Catalog(game).appearance_options
    for code in options['headtypecode'][:5]:
        nodes = glb_nodes(preview.head_glb(game, code))
        assert set(nodes) == {'head', 'eyes'}
        assert 1.4 < nodes['head']['min'][1] < nodes['head']['max'][1] < 1.9  # meters, standing player
    assert preview.hair_glb(game, 0) is None  # bald
    assert set(glb_nodes(preview.hair_glb(game, 10))) == {'cap', 'strands'}
    assert set(glb_nodes(preview.hair_glb(game, 25))) == {'cap'}


def test_face_texture_follows_the_game_rule(game):
    a = {'headtypecode': 10, 'eyebrowcode': 2, 'sideburnscode': 1, 'facialhaircolorcode': 3,
         'facialhairtypecode': 6, 'skintypecode': 1, 'skintonecode': 7}
    # faceType falls back to 0 and skin tone 7 becomes 8 (player.lua)
    assert preview.face_entry(game, a) == 'data/sceneassets/faces/face_0_1_0_2_1_3_6_1_8_textures.rx3'
    assert Image.open(io.BytesIO(preview.face_png(game, a))).size == (256, 512)


def test_hair_texture_and_colors(game):
    assert Image.open(io.BytesIO(preview.hair_color_png(game, 10))).mode == 'RGB'
    im = Image.open(io.BytesIO(preview.hair_alpha_png(game, 22, 'strands')))
    assert im.mode == 'L' and im.getextrema()[1] > 200  # atlas of curls (blue channel of hair_coeff)
    assert preview.hair_color(1) == '#0e0e0d' and preview.hair_color(99) == '#ff0000'


def test_body_and_team_kit(game):
    codes = {'jersey': 1, 'shorts': 0, 'socks': 2, 'arms': 1, 'legs': 2, 'shoes': 503, 'gloves': 0}
    nodes = {part: glb_nodes(preview.body_part_glb(game, part, code))[part] for part, code in codes.items()}
    assert nodes['shoes']['min'][1] < 0.05 < 1.5 < nodes['jersey']['max'][1]  # feet on the ground, cm -> m
    spots = preview._hotspots(preview._rx3(game, preview.ASSETS + preview.KIT_TEMPLATE))
    assert set(spots) == {'jersey', 'shorts'} and 'team' in spots['jersey']
    crest = Image.new('RGBA', (64, 64), (255, 0, 0, 255))
    jersey = Image.open(io.BytesIO(preview.kit_png(game, 'jersey', (0, 0, 255), crest))).convert('RGB')
    l, t, r, b = spots['jersey']['team']
    cx, cy = (l + r) / 2 * jersey.width, (t + b) / 2 * jersey.height
    red, _, blue = jersey.getpixel((int(cx), int(cy)))
    assert red > blue  # crest decal on the chest, rest of the jersey blue
    assert Image.open(io.BytesIO(preview.skin_png(game, 2))).size[0] > 0
    assert preview.glove_png(game, 0) == preview.glove_png(game, 1) != preview.glove_png(game, 49)


def test_street_kit_options_and_masks(game):
    options = preview.street_options(game)
    assert options['top'][20] and options['bottom'][0] and options['socks'][3]
    mask = Image.open(io.BytesIO(preview.street_png(game, 'top', 20, 5)))
    assert mask.mode == 'RGBA'  # RGB = color mask, alpha = shading
    assert set(preview.STREET_ARMS) == set(options['top'])  # every top style knows its sleeve length


def test_real_kit_texture_and_collar_mesh(game):
    """Real kits in the viewer: the PNG resized to the game's texture and shaded; the jersey mesh of its collar."""
    png = preview.real_kit_png(game, 'shorts', Image.new('RGB', (2048, 1024), (250, 250, 250)))
    im = Image.open(io.BytesIO(png))
    assert im.size == (1024, 512)
    assert max(im.convert('L').getextrema()) <= 250  # shaded by the occlusion map
    assert preview.body_part_glb(game, 'jersey', 0, 8) != preview.body_part_glb(game, 'jersey', 0)
