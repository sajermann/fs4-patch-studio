"""Generic kit (solid color + crest) for a team's Team Home/Away, plus the kit-screen thumbnail.

Reads the kit of TEMPLATE_TEAM (data3: data/sceneassets/kit/kit_<teamid>_<kind>_0.rx3), repaints jersey_cm /
shorts_cm / crest_cm, re-packs it as chunkzip and returns it named by the new team's id: a loose file under Game/
(the game opens it from disk).
Thumbnail: data/ui/imgassets/kits/j<kind>_<teamid:05d>.dds (DXT5 256x256), made from the white World XI jersey
(j0_111072) tinted with the jersey color + crest.
kind: 0 = Team Home, 1 = Team Away, 2 = goalkeeper (real kits only).

Real kits (build_real): a FIFA 14-16 kit (jersey 2048x2048 and shorts 2048x1024 PNGs, same UV as the game's) drawn
into the template's jersey_cm / shorts_cm (fsmod.dxt), grown from 1024x1024 / 1024x512 to REAL_TEXTURES when the
source is bigger (validated in game 11/11/2026: up close at 4K a texel of the 1024 jersey covered ~3.5-4 screen pixels,
~1.8 at 2048; 120 FPS kept), with the FIFA 16 position table of names/numbers
(REAL_POSITIONS), the template's crest_cm made transparent (the crest is painted on the kit) and the thumbnail of the
pack (or the generic one). Validated in game with Corinthians and Palmeiras.
"""
import io
import re
import struct
from collections import Counter

from PIL import Image, ImageChops

from . import chunk, rx3tex
from . import crest as crest_module
from .scanface import resize_texture

THUMBNAIL_TEMPLATE = 'data/ui/imgassets/kits/j0_111072.dds'
TEMPLATE_TEAM = 1932  # Barnsley (FIFA 12, not in Street): its kits were the first validated in game
POSITIONS_SECTION = 0xF55B1A1A  # names/numbers/crest rectangles of a kit rx3 (u0, v0, u1, v1 in the textures)
# FIFA 16 position table (Corinthians 2026 kit by Sabalero1905, the same in its 3 kits), validated in game with a
# PNG-only kit too (Palmeiras); file order: jersey team, numberback, numberfront, name, name_arccenter,
# name_arctangent, shorts team, number
REAL_POSITIONS = (
    ('team', (0.5387740135192871, 0.5619750022888184, 0.5923165082931519, 0.6101524233818054)),
    ('numberback', (0.5851367712020874, 0.33458900451660156, 0.4148631989955902, 0.19520699977874756)),
    ('numberfront', (0.46006712317466736, 0.694287121295929, 0.5400000214576721, 0.7602528929710388)),
    ('name', (0.5846976041793823, 0.37545791268348694, 0.4153023958206177, 0.3398227095603943)),
    ('name_arccenter', (0.5, 0.2661130130290985, 0.5, 0.2661130130290985)),
    ('name_arctangent', (0.5, 0.43212899565696716, 0.5, 0.43212899565696716)),
    ('team', (0.34078681468963623, 0.8106911778450012, 0.4107363820075989, 0.9162169694900513)),
    ('number', (0.5849999785423279, 0.754967212677002, 0.6551606059074402, 0.8554952144622803)),
)
# teamkits.numbercolor / shortsnumbercolor: palette of the game (same as FIFA); 1 white, 2 black, ... 19 dark green
NUMBER_COLORS = (*range(1, 18), 19)
COLLARS = range(15)  # teamkits.jerseycollargeometrytype: the game has body/jersey_<collar>_* meshes 0-14
REAL_TEXTURES = {'jersey_cm': (2048, 2048), 'shorts_cm': (2048, 1024)}  # real kit textures (the packs' size)
THUMBNAIL_SIDES = (256, 512)  # kit-screen thumbnail: 512 when the source is bigger than 256 (validated in game)
# largest stored source per real kit image (fsapi.project_store reduces bigger ones when the project is saved)
REAL_SOURCE_MAX = {'jersey': REAL_TEXTURES['jersey_cm'], 'shorts': REAL_TEXTURES['shorts_cm'],
                   'thumbnail': (THUMBNAIL_SIDES[-1],) * 2}
THUMBNAIL_CREST_LEVEL = 128  # width of the crest_cm level the kit-screen thumbnail is drawn from
JERSEY_RATIO, SHORTS_RATIO = 1, 2  # width / height of the kit PNGs (2048x2048, 2048x1024)


def kit_name(teamid, kind):
    return f'data/sceneassets/kit/kit_{teamid}_{kind}_0.rx3'


def thumbnail_name(teamid, kind):
    return f'data/ui/imgassets/kits/j{kind}_{teamid:05d}.dds'


def thumbnail(game, rgb, crest):
    """(PIL image, DDS bytes) of the kit-screen thumbnail."""
    template = Image.open(io.BytesIO(chunk.decode(game.read_entry(THUMBNAIL_TEMPLATE)[2]))).convert('RGBA')
    shade = template.convert('L').point(lambda v: min(255, int(v / 0.92))).convert('RGB')
    im = ImageChops.multiply(shade, Image.new('RGB', template.size, rgb)).convert('RGBA')
    im.putalpha(template.split()[3])
    im.alpha_composite(crest.convert('RGBA').resize((26, 26), Image.LANCZOS), (150, 50))
    buf = io.BytesIO()
    im.save(buf, format='DDS', pixel_format='DXT5')
    return im, buf.getvalue()


def erase_badge(d):
    """Paints over the original team's crest "badge" in jersey_coeff (chest stain) with the surrounding fabric."""
    t = rx3tex.by_name(d, 'jersey_coeff')
    im = rx3tex.to_image(d, t).convert('RGBA')
    w, h = im.size
    box = (int(w * .15), int(h * .35), int(w * .85), int(h * .65))
    region = im.crop(box)
    pixels = region.get_flattened_data() if hasattr(region, 'get_flattened_data') else region.getdata()
    dominant = Counter(pixels).most_common(1)[0][0]
    px = im.load()
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            r, g, b, _ = px[x, y]
            if g > r + 60 and g > b:  # teal color of the badge
                px[x, y] = dominant
    rx3tex.set_image(d, t, im)


def build(game, teamid, kind, jersey, shorts=None, crest=None, background=(255, 255, 255),
          erase_original_badge=False, log=print):
    """Returns {loose file name: bytes}: kit rx3 + thumbnail of teamid, made from TEMPLATE_TEAM's kit.
    crest = PIL image or None."""
    k, off, orig = game.read_entry(kit_name(TEMPLATE_TEAM, kind))
    name = kit_name(teamid, kind)
    d = bytearray(chunk.decode(orig))
    rx3tex.fill_solid(d, rx3tex.by_name(d, 'jersey_cm'), tuple(jersey))
    if shorts:
        rx3tex.fill_solid(d, rx3tex.by_name(d, 'shorts_cm'), tuple(shorts))
    if crest is not None:
        # transparent pixels get the background color (the originals use white); crest_cm is DXT3, made 256 px
        d = crest_module.set_texture(d, crest, background)
    if erase_original_badge:
        erase_badge(d)
    packed = chunk.chunkzip(bytes(d))
    log(f'{name}: {len(packed)} bytes')
    out = {name: packed}
    t = rx3tex.by_name(d, 'crest_cm')
    # the thumbnail's crest (26 px) comes from the 128 px level, the size of the template's own crest_cm: the
    # thumbnails stay the ones validated in game before crest_cm grew to 256
    level = next((i for i, (_, _, w, _) in enumerate(t['levels']) if w <= THUMBNAIL_CREST_LEVEL), 0)
    crest_img = rx3tex.to_image(d, t, level)
    _, dds = thumbnail(game, tuple(jersey), crest_img)
    out[thumbnail_name(teamid, kind)] = chunk.chunkzip(dds, 0x40000)
    return out


def _positions(d):
    """[(name, offset of its 4 floats)] of the position table, in file order."""
    off, size = next((o, s) for t, o, s, _ in rx3tex._sections(d) if t == POSITIONS_SECTION)
    p, end, out = off + 16, off + size, []
    while p < end:
        m = re.match(rb'([a-z_]+)\0', d[p:end])
        if not m:
            break
        name = m.group(1).decode()
        p += len(m.group(0))
        if name in ('jersey', 'shorts'):
            p += 1  # entry count
            continue
        out.append((name, p))
        p += 16
    return out


def set_positions(d, table=REAL_POSITIONS):
    """Writes a position table into a kit rx3 (big-endian, d = bytearray)."""
    entries = _positions(d)
    if [n for n, _ in entries] != [n for n, _ in table]:
        raise ValueError('unexpected kit position table')
    for (_, p), (_, values) in zip(entries, table):
        d[p:p + 16] = struct.pack('>4f', *values)


def clear_crest(d):
    """crest_cm fully transparent (DXT3: alpha 0, white): the real kit has the crest painted in."""
    t = rx3tex.by_name(d, 'crest_cm')
    block = rx3tex.swap16(struct.pack('<8sHHI', b'\0' * 8, 0xFFFF, 0xFFFF, 0))
    for q, n, _, _ in t['levels']:
        d[q:q + n] = block * (n // len(block))


def dominant_color(img, box=(.3, .55, .7, .95)):
    """Most common color of a region of the jersey texture (default: the front), for the generic thumbnail."""
    w, h = img.size
    region = img.convert('RGB').crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))
    region = region.resize((64, 64)).quantize(8).convert('RGB')
    pixels = region.get_flattened_data() if hasattr(region, 'get_flattened_data') else region.getdata()
    return Counter(pixels).most_common(1)[0][0]


def limited_size(part, size):
    """(width, height) of a stored real kit image (part: jersey / shorts / thumbnail) fitted into REAL_SOURCE_MAX, or
    None when it already fits."""
    scale = min(REAL_SOURCE_MAX[part][0] / size[0], REAL_SOURCE_MAX[part][1] / size[1])
    if scale >= 1:
        return None
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def set_real_texture(d, name, img):
    """rx3 data (bytearray) with texture `name` (jersey_cm / shorts_cm, DXT1) holding img; the texture grows to
    REAL_TEXTURES[name] when img is wider than it. Returns the (possibly new) bytearray."""
    t = rx3tex.by_name(d, name)
    size = REAL_TEXTURES[name]
    if img.width > t['w'] and (t['w'], t['h']) != size:
        d = bytearray(resize_texture(d, t, *size))
    rx3tex.set_image_dxt1(d, rx3tex.by_name(d, name), img)
    return d


def thumbnail_dds(img):
    """Kit-screen thumbnail file from a ready image (the pack's j<kind>_<id>.png / -MK.png, 256x256): 512 px when
    the image is bigger than 256 (THUMBNAIL_SIDES)."""
    side = THUMBNAIL_SIDES[1] if max(img.size) > THUMBNAIL_SIDES[0] else THUMBNAIL_SIDES[0]
    im = img.convert('RGBA').resize((side, side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format='DDS', pixel_format='DXT5')
    return chunk.chunkzip(buf.getvalue(), 0x40000)


def build_real(game, teamid, kind, jersey, shorts, thumb=None, crest=None, log=print):
    """Returns {loose file name: bytes}: kit rx3 + thumbnail of teamid from a FIFA 14-16 kit.
    jersey/shorts/thumb/crest = PIL images (thumb None: the generic thumbnail tinted with the jersey's front color)."""
    d = bytearray(chunk.decode(game.read_entry(kit_name(TEMPLATE_TEAM, 0))[2]))
    d = set_real_texture(d, 'jersey_cm', jersey)
    d = set_real_texture(d, 'shorts_cm', shorts)
    set_positions(d)
    clear_crest(d)
    erase_badge(d)
    name = kit_name(teamid, kind)
    packed = chunk.chunkzip(bytes(d))
    log(f'{name}: {len(packed)} bytes (real kit)')
    if thumb is not None:
        dds = thumbnail_dds(thumb)
    else:
        crest_img = crest if crest is not None else Image.new('RGBA', (26, 26), (0, 0, 0, 0))
        dds = chunk.chunkzip(thumbnail(game, dominant_color(jersey), crest_img)[1], 0x40000)
    return {name: packed, thumbnail_name(teamid, kind): dds}
