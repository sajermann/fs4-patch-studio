"""Team crest shown in the menus: three DDS files in data1 (licensed_large/medium/small/l<teamid>.dds).

Each one is a 'chunkzip' with a DXT5 DDS (no mips). The originals are 256/128/64 px; the app writes them at
UI_OUTPUT (512/512/256): every screen draws a crest file at a fixed size whatever the file's size, and these are the
sizes a 4K screen (ReStreet internal resolution 3x) needs. Measured in game on ReStreet 2.1.4 (largest drawn width
of each file at 4K: large 510 px in the team selector, medium 338 px in the goal banner, small ~180 px in the team
grid) and validated with bigger files (large 1024 is accepted too, only useful at internal resolution 4x).
A new team (a teamid the game does not know) gets them as loose files under Game/; the files of a
FIFA 12 team (TEMPLATE_TEAM) give the DDS header and the chunk wrapper.
Also the 3D crest (data/sceneassets/crest/crest_<teamid>.rx3, data3) that some street clothes patterns draw, and
the crest_cm of the kits (fsmod.kit): both 128 px textures in the originals, written at TEXTURE_SIZE (256; the
texture is reallocated in the rx3; drawn up to ~250 px wide at 4K, validated in game).
Source images bigger than MAX_SOURCE are reduced when the project is saved (fsapi.project_store): no screen draws
more than that, and a 3840 px source made every build slow.
"""
import io
import struct

from PIL import Image

from . import chunk, imageprep, rx3tex
from .scanface import resize_texture

UI_SIZES = (('large', 256), ('medium', 128), ('small', 64))  # original sizes
UI_OUTPUT = {'large': 512, 'medium': 512, 'small': 256}  # sizes the app writes (4K)
TEXTURE_SIZE = 256  # crest_cm of the 3D crest and of the kits
MAX_SOURCE = 1024  # largest side of a stored crest image
TEMPLATE_TEAM = 1932  # Barnsley (FIFA 12, not in Street): first team validated in game
SCENE_TEMPLATE_TEAM = 974  # Korea Republic: its 3D crest file was the first validated in game
CHUNK_SIZE = 184320  # chunk size of the game's own UI images (a 512x512 stadium image uses 2 chunks)


def ui_crest_name(size_label, teamid):
    return f'data/ui/imgassets/crest/licensed_{size_label}/l{teamid}.dds'


def limited_size(size):
    """(width, height) with size's aspect and the largest side MAX_SOURCE, or None when size already fits."""
    if max(size) <= MAX_SOURCE:
        return None
    scale = MAX_SOURCE / max(size)
    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def square(img):
    """Centers img on a transparent square canvas."""
    side = max(img.size)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def dds_entry(template, img):
    """chunkzip entry with img as a DXT5 DDS, reusing the DDS header (size fields updated) and trailer of an
    original single-image entry (template)."""
    raw = chunk.unchunk_single(template)
    old_w = struct.unpack('<I', raw[16:20])[0]
    old_h = struct.unpack('<I', raw[12:16])[0]
    w, h = img.size
    buf = io.BytesIO()
    imageprep.clean(img).save(buf, format='DDS', pixel_format='DXT5')
    pixels = buf.getvalue()[128:128 + w * h]
    assert len(pixels) == w * h
    header = bytearray(raw[:128])
    struct.pack_into('<III', header, 12, h, w, w * h)  # height, width, linear size (DXT5: 1 byte per pixel)
    return chunk.chunkzip(bytes(header) + pixels + raw[128 + old_w * old_h:], CHUNK_SIZE)


def ui_crest_images(img):
    """{size label: PIL image} of the three menu crests."""
    canvas = square(img.convert('RGBA'))
    return {label: canvas.resize((UI_OUTPUT[label],) * 2, Image.LANCZOS) for label, _ in UI_SIZES}


def ui_crest_files(game, teamid, img):
    """{loose file name: bytes} of the three menu crests of teamid."""
    out = {}
    for label, im in ui_crest_images(img).items():
        _, _, template = game.read_entry(ui_crest_name(label, TEMPLATE_TEAM))
        out[ui_crest_name(label, teamid)] = dds_entry(template, im)
    return out


def scene_crest_name(teamid):
    return f'data/sceneassets/crest/crest_{teamid}.rx3'


def set_texture(d, img, bg=(255, 255, 255)):
    """rx3 data (bytearray) with its crest_cm holding img at TEXTURE_SIZE (the texture is reallocated when the file
    has a smaller one); transparent pixels get bg. Returns the (possibly new) bytearray."""
    t = rx3tex.by_name(d, 'crest_cm')
    if t['w'] < TEXTURE_SIZE:
        d = bytearray(resize_texture(d, t, TEXTURE_SIZE, TEXTURE_SIZE))
        t = rx3tex.by_name(d, 'crest_cm')
    rx3tex.set_image(d, t, square(img.convert('RGBA')), bg=tuple(bg))
    return d


def scene_crest_files(game, teamid, img):
    """{loose file name: bytes} of the 3D crest of teamid (crest_cm, DXT1, TEXTURE_SIZE), drawn by the street clothes
    patterns that carry the team badge; without it the game shows its missing-texture checkerboard there.
    Made from an original team's file (SCENE_TEMPLATE_TEAM); transparent pixels become white, like the kits."""
    _, _, orig = game.read_entry(scene_crest_name(SCENE_TEMPLATE_TEAM))
    d = set_texture(bytearray(chunk.decode(orig)), img)
    return {scene_crest_name(teamid): chunk.chunkzip(bytes(d))}


def original_crest(game, teamid, size_label='medium'):
    """PIL image of an original team's menu crest, or None when the game has none (its internal teams)."""
    entry = game.read_entry(ui_crest_name(size_label, teamid))
    return Image.open(io.BytesIO(chunk.decode(entry[2]))) if entry else None
