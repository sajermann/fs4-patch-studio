"""League image in the menus = the flag of the league's COUNTRY: the league selector ("Select Team") shows
data/ui/artassets/countryflagssmall/f_<countryid>.big (78x78) in the grid and countryflagsalt/f_<countryid>.big
(250x116) once the league is chosen (validated in game, 20/10/2026; notfound.big is the fallback). New leagues
take a country no nation uses (builder.IMAGE_COUNTRIES, validated 22/10), so their flags are loose files under
Game/ (the game opens d:/<name> from disk when no archive has it). Entries added to data1's directory and .bh,
or existing entries renamed, are NOT found by the game (tested).
(data/ui/artassets/leaguelogos{,_sm,_tiny}/l<leagueid>.big have the same format but were not seen in game.)

Each file is a 'chunklzx' with a BIGF archive (the EA "Apt" UI format) holding: '0' (Apt data, one image shape),
'1' (Apt constants), '3' (shape geometry: height as float at 0x64, width at 0xA0), 'sg1'/'sg2' (empty) and '2'
(the image, RefPack-compressed). The image is an XPR2 texture: DXT5, Xbox 360 tiled, 16-bit byte swapped, the
shape drawn 1:1 from its top-left corner. Apart from the shape size, the Apt entries are identical in every file
of a folder, so every new image is built from one template file of the right size.

New images are written at SCALE (4x) the original size and uncompressed (texture format 8_8_8_8 instead of DXT5,
no RefPack): the menus scale them down to the original size, much sharper (validated in game, 20/10/2026). The
archive goes back as a 'chunkzip'.
"""
import io
import struct

from PIL import Image

from . import chunk, imageprep

# asset: (folder, file prefix, keyed by, template id, region drawn, maximum image box inside it, alignment)
ASSETS = {
    'flag_small': ('countryflagssmall', 'f_', 'country', 216, (78, 78), (74, 74), 'center'),
    'flag_wide': ('countryflagsalt', 'f_', 'country', 216, (250, 116), (242, 110), 'center'),
}
IMAGE_ENTRY, GEOMETRY_ENTRY = '2', '3'
XPR_FETCH = 0x2C + 28  # GPU texture fetch constant (6 big-endian u32) inside the XPR2 header
FMT_DXT5, FMT_RGBA = 0x14, 0x06
SCALE = 4  # new images are written at 4x the original size (the menus scale them down; validated in game)


def asset_name(asset, key):
    folder, prefix = ASSETS[asset][:2]
    return f'data/ui/artassets/{folder}/{prefix}{key}.big'


def read_bigf(data):
    """([(name, bytes)] in directory order, header bytes after the directory) of a BIGF archive."""
    if data[:4] != b'BIGF':
        raise ValueError('not a BIGF archive')
    n, hdr_len = struct.unpack('>II', data[8:16])
    pos, out = 16, []
    for _ in range(n):
        off, size = struct.unpack('>II', data[pos:pos + 8])
        end = data.index(b'\0', pos + 8)
        out.append((data[pos + 8:end].decode('ascii'), data[off:off + size]))
        pos = end + 1
    return out, data[pos:hdr_len]


def write_bigf(entries, header_tail=b''):
    """BIGF archive laid out like the originals: header_tail (e.g. b'L286' + version) after the directory and
    counted in the header length, 64-byte aligned data, the end of the last entry little-endian at 4 and the
    file padded to 16 bytes. The originals also end with 16 unknown bytes (not an MD5 of the content); like the
    ReStreet installer, they are not written."""
    hdr_len = 16 + sum(9 + len(name) for name, _ in entries) + len(header_tail)
    out = bytearray(-(-hdr_len // 64) * 64)
    directory, end = bytearray(), len(out)
    for name, data in entries:
        out += bytes(-len(out) % 64)
        directory += struct.pack('>II', len(out), len(data)) + name.encode('ascii') + b'\0'
        out += data
        end = len(out)
    out += bytes(-len(out) % 16)
    out[:hdr_len] = (b'BIGF' + struct.pack('<I', end) + struct.pack('>II', len(entries), hdr_len) + directory
                     + header_tail)
    return bytes(out)


def refpack_decode(b):
    """Decompresses EA RefPack (10 FB header); returns the input unchanged when it is not RefPack."""
    if b[:2] != b'\x10\xfb':
        return b
    length, p, out = int.from_bytes(b[2:5], 'big'), 5, bytearray()
    while len(out) < length:
        c = b[p]
        p += 1
        copies = distance = 0
        if c < 0x80:
            literals, copies, distance = c & 3, ((c & 0x1C) >> 2) + 3, ((c & 0x60) << 3) + b[p] + 1
            p += 1
        elif c < 0xC0:
            literals, copies, distance = b[p] >> 6, (c & 0x3F) + 4, ((b[p] & 0x3F) << 8) + b[p + 1] + 1
            p += 2
        elif c < 0xE0:
            literals = c & 3
            copies = ((c & 0x0C) << 6) + b[p + 2] + 5
            distance = ((c & 0x10) << 12) + (b[p] << 8) + b[p + 1] + 1
            p += 3
        elif c < 0xFC:
            literals = ((c & 0x1F) << 2) + 4
        else:
            literals = c & 3
        out += b[p:p + literals]
        p += literals
        for _ in range(copies):
            out.append(out[-distance])
        if c >= 0xFC:
            break
    if len(out) != length:
        raise ValueError('truncated RefPack data')
    return bytes(out)


def _tiled(x, y, pitch, log_bpp):
    """Index of element (x, y) in Xbox 360 tiled memory (XGAddress2DTiledOffset; elements of 2**log_bpp bytes:
    16-byte DXT blocks or 4-byte texels)."""
    aligned = (pitch + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (aligned >> 5)) << (log_bpp + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << log_bpp
    off = macro + ((micro & ~15) << 1) + (micro & 15) + ((y & 8) << (3 + log_bpp)) + ((y & 1) << 4)
    return (((off & ~511) << 3) + ((off & 448) << 2) + (off & 63) + ((y & 16) << 7)
            + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6)) >> log_bpp


def _order(w, h, pitch, log_bpp):
    """[(linear offset, tiled offset)] of the w x h elements of a texture."""
    size = 1 << log_bpp
    return [((y * w + x) * size, _tiled(x, y, pitch, log_bpp) * size) for y in range(h) for x in range(w)]


def _swap16(b):
    a = bytearray(len(b))
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)


def texture_info(xpr):
    """(format, width, height, pitch, data offset) of a tiled XPR2 texture (DXT5 or RGBA)."""
    if xpr[:4] != b'XPR2':
        raise ValueError('not an XPR2 texture')
    fetch = struct.unpack('>6I', xpr[XPR_FETCH:XPR_FETCH + 24])
    fmt = fetch[1] & 0x3F
    if (fmt, (fetch[1] >> 6) & 3) not in ((FMT_DXT5, 1), (FMT_RGBA, 0)) or not fetch[0] >> 31:
        raise ValueError('unexpected XPR2 texture format')
    w, h = (fetch[2] & 0x1FFF) + 1, ((fetch[2] >> 13) & 0x1FFF) + 1
    return fmt, w, h, ((fetch[0] >> 22) & 0x1FF) * 32, 12 + struct.unpack('>I', xpr[4:8])[0]


def _dds(w, h, pixels):
    return (b'DDS ' + struct.pack('<7I', 124, 0x1007, h, w, len(pixels), 0, 1) + b'\0' * 44
            + struct.pack('<2I4s5I', 32, 4, b'DXT5', 0, 0, 0, 0, 0) + struct.pack('<5I', 0x1000, 0, 0, 0, 0)
            + pixels)


def xpr_to_image(xpr):
    """Whole texture as a PIL image."""
    fmt, w, h, pitch, start = texture_info(xpr)
    data = xpr[start:]
    if fmt == FMT_RGBA:
        linear = bytearray(w * h * 4)
        for lin, tiled in _order(w, h, pitch, 2):
            linear[lin:lin + 4] = data[tiled:tiled + 4]
        return Image.frombytes('RGBA', (w, h), bytes(linear))
    linear = bytearray(w * h)
    for lin, tiled in _order(w // 4, h // 4, pitch // 4, 4):
        linear[lin:lin + 16] = data[tiled:tiled + 16]
    return Image.open(io.BytesIO(_dds(w, h, _swap16(linear)))).convert('RGBA')


def rgba_xpr(template, img):
    """XPR2 texture with img uncompressed (format 8_8_8_8, RGBA bytes, no byte swap; validated in game), reusing
    the header of template (an original DXT5 texture of any size)."""
    w, h = img.size
    pixels, data = imageprep.clean(img).tobytes(), bytearray(w * h * 4)
    for lin, tiled in _order(w, h, w, 2):
        data[tiled:tiled + 4] = pixels[lin:lin + 4]
    header = bytearray(template[:12 + struct.unpack('>I', template[4:8])[0]])
    struct.pack_into('>I', header, 8, len(data))
    fetch = list(struct.unpack('>6I', header[XPR_FETCH:XPR_FETCH + 24]))
    fetch[0] = (fetch[0] & ~(0x1FF << 22)) | ((w // 32) << 22)  # pitch
    fetch[1] = (fetch[1] & ~0xFF) | FMT_RGBA  # format, endian 0
    fetch[2] = (w - 1) | ((h - 1) << 13)
    struct.pack_into('>6I', header, XPR_FETCH, *fetch)
    return bytes(header) + bytes(data)


def shape_size(geometry):
    """(width, height) of the shape, from the geometry entry."""
    return int(struct.unpack('>f', geometry[0xA0:0xA4])[0]), int(struct.unpack('>f', geometry[0x64:0x68])[0])


def read_image(entry):
    """(PIL image of the region drawn, its size) of an Apt image file."""
    files = dict(read_bigf(chunk.decode(entry))[0])
    w, h = shape_size(files[GEOMETRY_ENTRY])
    return xpr_to_image(refpack_decode(files[IMAGE_ENTRY])).crop((0, 0, w, h)), (w, h)


def place(img, asset, fit='contain'):
    """img on a transparent canvas the size of the region drawn (times SCALE): 'contain' = whole image fitted
    (aspect kept) into the image box, centered; 'cover' = the region filled, the overflow cropped."""
    region, box = [(a * SCALE, b * SCALE) for a, b in ASSETS[asset][4:6]]
    img = img.convert('RGBA')
    bbox = img.getchannel('A').getbbox()
    if bbox:
        img = img.crop(bbox)
    target = region if fit == 'cover' else box
    scale = (max if fit == 'cover' else min)(target[0] / img.width, target[1] / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    if fit == 'cover':
        left, top = (img.width - region[0]) // 2, (img.height - region[1]) // 2
        img = img.crop((left, top, left + region[0], top + region[1]))
    canvas = Image.new('RGBA', region, (0, 0, 0, 0))
    canvas.paste(img, ((region[0] - img.width) // 2, (region[1] - img.height) // 2))
    return canvas


def _scale_shape(apt_data, geometry, size, new_size):
    """Apt entries '0' and '3' with the shape size changed (u32 pair at 0x40 of '0', floats in both)."""
    apt_data = bytearray(apt_data)
    if struct.unpack('>II', apt_data[0x40:0x48]) != size:
        raise ValueError('unexpected Apt data layout')
    struct.pack_into('>II', apt_data, 0x40, *new_size)
    out = []
    for d in (bytes(apt_data), geometry):
        for old, new in sorted(zip(size, new_size), reverse=True):  # larger first: a shared value is replaced once
            d = d.replace(struct.pack('>f', old), struct.pack('>f', new))
        out.append(d)
    return out


def image_entry(template, asset, img, fit='contain'):
    """chunkzip Apt file showing img at SCALE times the original size, uncompressed, built from an original file
    of asset's folder (template). The menus draw it at the original size (validated in game: sharper)."""
    files, header_tail = read_bigf(chunk.decode(template))
    by_name = dict(files)
    region = ASSETS[asset][4]
    if shape_size(by_name[GEOMETRY_ENTRY]) != region:
        raise ValueError(f'{asset}: template shape is {shape_size(by_name[GEOMETRY_ENTRY])}, expected {region}')
    scaled = (region[0] * SCALE, region[1] * SCALE)
    by_name['0'], by_name[GEOMETRY_ENTRY] = _scale_shape(by_name['0'], by_name[GEOMETRY_ENTRY], region, scaled)
    xpr = refpack_decode(by_name[IMAGE_ENTRY])
    _, w, h, _, _ = texture_info(xpr)
    texture = Image.new('RGBA', (w * SCALE, h * SCALE), (0, 0, 0, 0))
    texture.paste(place(img, asset, fit), (0, 0))
    by_name[IMAGE_ENTRY] = rgba_xpr(xpr, texture)
    return chunk.chunkzip(write_bigf([(name, by_name[name]) for name, _ in files], header_tail))


def flag_files(game, countryid, img, wide_img=None, wide_fit='contain'):
    """{internal name: Apt file bytes} for the two flags of countryid: img in the small square one and wide_img
    (default img) in the wide one, placed by wide_fit ('contain' or 'cover')."""
    out = {}
    for asset, (_, _, _, template_id, _, _, _) in ASSETS.items():
        template = game.read_entry(asset_name(asset, template_id))[2]
        wide = asset == 'flag_wide'
        out[asset_name(asset, countryid)] = image_entry(template, asset, (wide_img or img) if wide else img,
                                                        wide_fit if wide else 'contain')
    return out
