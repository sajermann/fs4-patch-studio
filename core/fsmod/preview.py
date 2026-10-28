"""3D preview of generic players (headclasscode 1): meshes as GLB and textures as PNG.

How the game assembles a generic head (data0: data/fifarna/lua/assets/player.lua):
  head    data/sceneassets/heads/head_<headtypecode>_1.rx3          meshes 'head' and 'eyes'
  face    data/sceneassets/faces/face_<faceType>_1_0_<eyebrowcode>_<sideburnscode>_<facialhaircolorcode>_
          <facialhairtypecode>_<skintypecode>_<skintonecode>_textures.rx3   (falls back to faceType 0, the only one
          shipped: all 3*2*5*8*3*7 combinations exist; skin tones 1, 3 and 7 become 2, 4 and 8). Skin, eyebrows
          and beard are baked into this texture.
  eyes    data/sceneassets/heads/eyes_<eyecolorcode>_1_textures.rx3
  hair    data/sceneassets/hair/hair_<hairtypecode>_1_0.rx3 (submeshes alphaA = cap, alphaB = strands, optional)
          + hair_<hairtypecode>_1_textures.rx3: hair_cm (grey, tinted with the hairColor constant) and hair_coeff
          (R = cap opacity, B = strands opacity). Cap and strands have 2 UV sets: t0 for the tiling hair_cm, t1 for
          hair_coeff (on the strands an atlas of curls/locks). hairtypecode 0 = bald (no files).
  hair colors: GetHairColorARGB, indexed by haircolorcode.

Body (PlayerAssetHighLod, team kits = not isFS4Player): body/jersey_<collar>_<sleeve>_<armband>_<tucked>_0.rx3
(sleeve = jerseysleevelengthcode, 1 = long), body/shorts.rx3, body/sock_<socklengthcode>.rx3,
body/arms_<sleeve>.rx3, body/legs_<socklengthcode>.rx3, shoe/shoe_<shoetypecode>.rx3 (+ shoe_<type>_0_textures).
Skin of arms/legs: body/skin_<skin tone>_textures.rx3 (body_<n>_cm). Kit: kit/kit_<team>_<kind>_0.rx3 jersey_cm and
shorts_cm (the socks are mapped on the top of shorts_cm, so they show the shorts color), crest_cm drawn as a decal
in the 'team' hotspot (section 0xF55B1A1A, UV rect), shaded by the occlusion maps kit/jersey_0_0_textures (jersey_am)
and kit/shorts_0_textures (shorts_am).
Street kits (isFS4Player, data7 + data3): meshes body/top_<style>_0_0_0_0.rx3, body/bottom_<style>.rx3,
body/socks_<style>.rx3 (legs_<style % 10>); textures clothes/<top|bottom|socks>_<style>_<pattern>_cm.rx3 are color MASKS
(red = primary, green = secondary, blue = tertiary, painted by the shader with kitColour*Pri/Sec/Ter) and
clothes/<part>_<style>_textures.rx3 holds the occlusion map. Long-sleeved tops use arms_1, short arms_0, tank top arms_2.
Goalkeeper gloves (accessory.lua, accessory model 18): gkglove/gkglove_0_0.rx3 + gkglove_0_<gkglovetypecode>_cm.rx3.
"""
import io
import re
import struct
from functools import lru_cache

from PIL import Image, ImageChops

from . import big, chunk, gltf, rx3mesh, rx3tex
from .crest import square

ASSETS = 'data/sceneassets/'
# player.lua GetHairColorARGB (index = haircolorcode); unknown codes are drawn red by the game
HAIR_COLORS = (0xEDAC57, 0x0E0E0D, 0xA07741, 0x1F160E, 0xFFD286, 0x6E4D2B, 0x3B2816, 0x683016,
               0xC8C9CF, 0x525355, 0x345A34, 0x263F67)
# submesh tag, hair_coeff channel with the opacity, UV set that samples hair_coeff (TEXCOORD_n)
# (submesh, hair_coeff channel, UV set): both read the coeff with the second UV set (24/10/2026: real faces like 71654
# have a different t0 on the cap and the game showed their front hair only as t1 does; generic caps give the same)
HAIR_PARTS = {'cap': ('alphaA', 0, 1), 'strands': ('alphaB', 2, 1)}
CM_TO_M = 0.01
HOTSPOTS = 0xF55B1A1A
KIT_TEMPLATE = 'kit/kit_112298_0_0.rx3'  # generic team template: only its hotspots are used
KIT_PARTS = {'jersey': ('jersey_cm', 'kit/jersey_0_0_textures.rx3', 'jersey_am'),
             'shorts': ('shorts_cm', 'kit/shorts_0_textures.rx3', 'shorts_am')}


def hair_color(code):
    return '#%06x' % (HAIR_COLORS[code] if 0 <= code < len(HAIR_COLORS) else 0xFF0000)


def _rx3(sources, name):
    entry = sources.read_entry(name)
    if entry is None:
        raise KeyError(name)
    return chunk.decode(entry[2])


def _png(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=False)
    return buf.getvalue()


def _glb_mesh(name, m):
    a = m['attrs']
    out = {'name': name, 'indices': m['indices'],
           'positions': [[c * CM_TO_M for c in p[:3]] for p in a['p0']],
           'uvs': a.get('t0'), 'uvs1': a.get('t1')}
    if 'n0' in a:
        out['normals'] = [[c / l for c in v] if (l := sum(c * c for c in v) ** 0.5) else [0, 1, 0] for v in a['n0']]
    return out


def head_glb_of(d):
    """GLB with nodes 'head' and 'eyes' of a head RX3 (generic, scanned or the far-camera LOD head)."""
    return gltf.write_glb([_glb_mesh('eyes' if 'eyes' in m['name'] else 'head', m) for m in rx3mesh.meshes(d)])


def hair_glb_of(d):
    """GLB with nodes 'cap' and/or 'strands' of a hair RX3 (hairlod: cap only)."""
    parts = []
    for m in rx3mesh.meshes(d):
        tag = next((p for p, (sub, _, _) in HAIR_PARTS.items() if f'_{sub}' in m['name']), 'cap')
        parts.append(_glb_mesh(tag, m))
    return gltf.write_glb(parts)


@lru_cache(maxsize=64)
def head_glb(sources, headtypecode):
    """GLB with nodes 'head' and 'eyes' of a generic head (meters, y up, face towards +z)."""
    return head_glb_of(_rx3(sources, f'{ASSETS}heads/head_{headtypecode}_1.rx3'))


@lru_cache(maxsize=64)
def hair_glb(sources, hairtypecode):
    """GLB with nodes 'cap' and/or 'strands', or None for bald (no hair files)."""
    if not hairtypecode:
        return None
    return hair_glb_of(_rx3(sources, f'{ASSETS}hair/hair_{hairtypecode}_1_0.rx3'))


LOD_HEAD = 'body/playerlod_head.rx3'  # head of every player at the normal play camera (LOD 1), scanned or not


@lru_cache(maxsize=1)
def lod_head_glb(sources):
    return head_glb_of(_rx3(sources, ASSETS + LOD_HEAD))


def face_entry(sources, a):
    """Face texture entry the game loads for appearance dict a (same rule and fallback as player.lua)."""
    tone = a.get('skintonecode', 2)
    tone = tone + 1 if tone in (1, 3, 7) else tone
    tail = '_'.join(str(a.get(f, 0)) for f in ('eyebrowcode', 'sideburnscode', 'facialhaircolorcode',
                                                  'facialhairtypecode', 'skintypecode'))
    for face_type in (a.get('headtypecode', 0), 0):
        name = f'{ASSETS}faces/face_{face_type}_1_0_{tail}_{tone}_textures.rx3'
        if sources.locate(name):
            return name
    raise KeyError(name)


def texture_png(d, index=0):
    """First (or index-th) texture of an RX3 as PNG (RGB)."""
    return _png(rx3tex.to_image(d, rx3tex.textures(d)[index]).convert('RGB'))


@lru_cache(maxsize=256)
def _face_png(sources, name):
    return texture_png(_rx3(sources, name))


def face_png(sources, appearance):
    return _face_png(sources, face_entry(sources, appearance))


@lru_cache(maxsize=16)
def eyes_png(sources, eyecolorcode):
    return texture_png(_rx3(sources, f'{ASSETS}heads/eyes_{eyecolorcode}_1_textures.rx3'))


def hair_color_png_of(d):
    """Grey hair color texture (hair_cm) of a hair textures RX3, tinted by the viewer; first UV set."""
    return _png(rx3tex.to_image(d, rx3tex.by_name(d, 'hair_cm')).convert('RGB'))


def hair_alpha_png_of(d, part):
    """Opacity of a hair submesh (grey image from its hair_coeff channel), sampled with HAIR_PARTS[part][2]."""
    coeff = rx3tex.to_image(d, rx3tex.by_name(d, 'hair_coeff')).convert('RGB')
    return _png(coeff.split()[HAIR_PARTS[part][1]])


@lru_cache(maxsize=64)
def hair_color_png(sources, hairtypecode):
    return hair_color_png_of(_rx3(sources, f'{ASSETS}hair/hair_{hairtypecode}_1_textures.rx3'))


@lru_cache(maxsize=64)
def hair_alpha_png(sources, hairtypecode, part):
    return hair_alpha_png_of(_rx3(sources, f'{ASSETS}hair/hair_{hairtypecode}_1_textures.rx3'), part)


def _hotspots(d):
    """{group: {name: (left, top, right, bottom) in UV}} of a kit RX3 (e.g. ['jersey']['team'] = crest area)."""
    for type_, off, size, _ in rx3mesh._sections(d):
        if type_ != HOTSPOTS:
            continue
        p, end, out = off + 16, off + size, {}

        def cstr(p):
            e = d.index(b'\0', p)
            return d[p:e].decode('ascii'), e + 1

        while p < end and d[p]:
            group, p = cstr(p)
            count, p = d[p], p + 1
            spots = out[group] = {}
            for _ in range(count):
                name, p = cstr(p)
                spots[name] = struct.unpack('>4f', d[p:p + 16])
                p += 16
        return out
    return {}


# body part -> file; code = jerseysleevelengthcode (jersey, arms), socklengthcode (socks, legs), shoetypecode (shoes);
# gloves: one mesh for every gkglovetypecode, already on the hands of the reference pose (accessory.lua, model 18)
BODY_PARTS = {'jersey': 'body/jersey_{collar}_{}_0_0_0.rx3', 'shorts': 'body/shorts.rx3', 'socks': 'body/sock_{}.rx3',
              'arms': 'body/arms_{}.rx3', 'legs': 'body/legs_{}.rx3', 'shoes': 'shoe/shoe_{}.rx3',
              'gloves': 'gkglove/gkglove_0_0.rx3',
              # street kit pieces (code = style)
              'top': 'body/top_{}_0_0_0_0.rx3', 'bottom': 'body/bottom_{}.rx3', 'streetsocks': 'body/socks_{}.rx3'}
STREET_MESH = {'top': 'top', 'bottom': 'bottom', 'socks': 'streetsocks'}  # street part -> BODY_PARTS key
STREET_ARMS = {0: 1, 1: 1, 10: 1, 23: 1, 20: 0, 21: 0, 22: 0, 24: 2}  # top style -> arms_<n> (long/short/tank top)
# full-length trousers (bottom mesh down to the ankles): the viewer hides legs and socks under them, otherwise the
# reference-pose legs poke through at the knees
STREET_FULL_LENGTH_BOTTOMS = (11, 12)
GLOVE_FALLBACK = 1  # gkglovetypecode 0 (most players) has no gkglove_0_0_cm file


@lru_cache(maxsize=64)
def body_part_glb(sources, part, code, collar=0):
    """GLB of one body part (nodes named after the part; team kit body, meters). One file per part so the viewer
    reloads only what changed. collar: jersey collar mesh (teamkits.jerseycollargeometrytype, 0-14)."""
    meshes = rx3mesh.meshes(_rx3(sources, ASSETS + BODY_PARTS[part].format(code, collar=collar)))
    return gltf.write_glb([_glb_mesh(part, m) for m in meshes])


def _first_texture_png(sources, name):
    d = _rx3(sources, ASSETS + name)
    return _png(rx3tex.to_image(d, rx3tex.textures(d)[0]).convert('RGB'))


@lru_cache(maxsize=16)
def skin_png(sources, tone):
    """Skin of arms and legs."""
    return _first_texture_png(sources, f'body/skin_{tone}_textures.rx3')


@lru_cache(maxsize=32)
def shoe_png(sources, shoe):
    return _first_texture_png(sources, f'shoe/shoe_{shoe}_0_textures.rx3')


@lru_cache(maxsize=32)
def glove_png(sources, code):
    """Goalkeeper glove color map gkglove/gkglove_0_<gkglovetypecode>_cm.rx3 (accessory.lua)."""
    name = f'gkglove/gkglove_0_{code}_cm.rx3'
    if not sources.locate(ASSETS + name):
        name = f'gkglove/gkglove_0_{GLOVE_FALLBACK}_cm.rx3'
    return _first_texture_png(sources, name)


@lru_cache(maxsize=8)
def _kit_base(sources, part):
    """(texture size, crest rect, occlusion image) of a kit part."""
    d = _rx3(sources, ASSETS + KIT_TEMPLATE)
    t = rx3tex.by_name(d, KIT_PARTS[part][0])
    rect = _hotspots(d).get(part, {}).get('team')
    am = _rx3(sources, ASSETS + KIT_PARTS[part][1])
    occlusion = rx3tex.to_image(am, rx3tex.by_name(am, KIT_PARTS[part][2])).convert('L')
    return (t['w'], t['h']), rect, occlusion


def kit_png(sources, part, rgb, crest=None):
    """Team kit texture as the game draws it: solid color (what the builder writes) + crest decal in the 'team'
    hotspot, shaded by the occlusion map. part: 'jersey' or 'shorts' (also used by the socks)."""
    size, rect, occlusion = _kit_base(sources, part)
    im = Image.new('RGBA', size, tuple(rgb) + (255,))
    if crest is not None and rect:
        box = _uv_box(rect, size)
        decal = square(crest.convert('RGBA')).resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        im.alpha_composite(decal, box[:2])
    shade = occlusion.resize(size, Image.BILINEAR).convert('RGB')
    return _png(ImageChops.multiply(im.convert('RGB'), shade))


def real_kit_png(sources, part, img):
    """Real kit texture (a FIFA 14-16 PNG, same UV as the game's, fsmod.kit.build_real) as the game draws it:
    resized to the game's texture and shaded by the occlusion map."""
    size, _, occlusion = _kit_base(sources, part)
    im = img.convert('RGB').resize(size, Image.LANCZOS)
    return _png(ImageChops.multiply(im, occlusion.resize(size, Image.BILINEAR).convert('RGB')))


@lru_cache(maxsize=4)
def street_options(sources):
    """{part: {style: [patterns]}} of the street clothes that have both a mesh (data3) and a mask (data7)."""
    names = [n for n, _, _ in big.read_toc_file(sources._path('data7.big'))]
    out = {'top': {}, 'bottom': {}, 'socks': {}}
    for name in names:
        m = re.fullmatch(r'data/sceneassets/clothes/(top|bottom|socks)_(\d+)_(\d+)_cm\.rx3', name)
        if m:
            part, style, pattern = m[1], int(m[2]), int(m[3])
            if sources.locate(ASSETS + BODY_PARTS[STREET_MESH[part]].format(style)):
                out[part].setdefault(style, []).append(pattern)
    return {part: {s: sorted(p) for s, p in sorted(styles.items())} for part, styles in out.items()}


@lru_cache(maxsize=256)
def street_png(sources, part, style, pattern):
    """Street clothes texture for the viewer: RGB = color mask (red/green/blue = primary/secondary/tertiary),
    alpha = occlusion map (shading)."""
    d = _rx3(sources, f'{ASSETS}clothes/{part}_{style}_{pattern}_cm.rx3')
    mask = rx3tex.to_image(d, rx3tex.textures(d)[0]).convert('RGB')
    am = _rx3(sources, f'{ASSETS}clothes/{part}_{style}_textures.rx3')
    occlusion = rx3tex.to_image(am, rx3tex.textures(am)[0]).convert('L').resize(mask.size, Image.BILINEAR)
    mask.putalpha(occlusion)
    return _png(mask)


def _uv_box(rect, size):
    """Pixel box (left, top, right, bottom) of a hotspot rect (UV, corners in any order) in a texture of size."""
    l, t, r, b = rect
    return (round(min(l, r) * size[0]), round(min(t, b) * size[1]), round(max(l, r) * size[0]), round(max(t, b) * size[1]))


@lru_cache(maxsize=256)
def _street_crest_box(sources, part, style, pattern):
    """(texture size, pixel box of the 'team' hotspot) of a street piece; box None when the pattern has no crest."""
    d = _rx3(sources, f'{ASSETS}clothes/{part}_{style}_{pattern}_cm.rx3')
    t = rx3tex.textures(d)[0]
    size = (t['w'], t['h'])
    for spots in _hotspots(d).values():  # one group: 'jersey' (tops) or 'shorts' (bottoms)
        box = _uv_box(spots['team'], size) if 'team' in spots else None
        if box and box[2] > box[0] and box[3] > box[1]:
            return size, box
    return size, None


def street_crest_png(sources, part, style, pattern, crest):
    """Decal laid over a street piece in the viewer (same UV as street_png): the team crest in the piece's 'team'
    hotspot, where the game draws data/sceneassets/crest/crest_<teamid>.rx3; transparent elsewhere. A pattern without
    crest (or no crest image) gives a tiny transparent image."""
    size, box = _street_crest_box(sources, part, style, pattern)
    if box is None or crest is None:
        return _png(Image.new('RGBA', (4, 4), (0, 0, 0, 0)))
    # bottoms have tall boxes (about 1:2): fitted keeping the crest's proportions, not checked in game
    side = min(box[2] - box[0], box[3] - box[1])
    decal = square(crest.convert('RGBA')).resize((side, side), Image.LANCZOS)
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    im.alpha_composite(decal, ((box[0] + box[2] - side) // 2, (box[1] + box[3] - side) // 2))
    return _png(im)
