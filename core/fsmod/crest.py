"""Team crest shown in the menus: three DDS files in data1 (licensed_large/medium/small/l<teamid>.dds).

Each one is a 'chunkzip' with a DXT5 DDS (no mips). The originals are 256/128/64 px; the app writes them at
SCALE times that size (validated in game on ReStreet 2.x: the menus draw them at the same size, sharper).
A new team (a teamid the game does not know) gets them as loose files under Game/; the files of a
FIFA 12 team (TEMPLATE_TEAM) give the DDS header and the chunk wrapper.
"""
import io
import struct

from PIL import Image

from . import chunk, imageprep

UI_SIZES = (('large', 256), ('medium', 128), ('small', 64))  # original sizes
SCALE = 2
TEMPLATE_TEAM = 1932  # Barnsley (FIFA 12, not in Street): first team validated in game
CHUNK_SIZE = 184320  # chunk size of the game's own UI images (a 512x512 stadium image uses 2 chunks)


def ui_crest_name(size_label, teamid):
    return f'data/ui/imgassets/crest/licensed_{size_label}/l{teamid}.dds'


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
    return {label: canvas.resize((px * SCALE, px * SCALE), Image.LANCZOS) for label, px in UI_SIZES}


def ui_crest_files(game, teamid, img):
    """{loose file name: bytes} of the three menu crests of teamid."""
    out = {}
    for label, im in ui_crest_images(img).items():
        _, _, template = game.read_entry(ui_crest_name(label, TEMPLATE_TEAM))
        out[ui_crest_name(label, teamid)] = dds_entry(template, im)
    return out


def original_crest(game, teamid, size_label='medium'):
    """PIL image of an original team's menu crest, or None when the game has none (its internal teams)."""
    entry = game.read_entry(ui_crest_name(size_label, teamid))
    return Image.open(io.BytesIO(chunk.decode(entry[2]))) if entry else None
