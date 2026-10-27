"""Textures inside RX3b files (Xbox 360, big-endian).

Texture section (type 0x7A0B60DA): u32 size | u8 1 | u8 format (0 DXT1, 1 DXT3, 3 ARGB) | u8 3 | u8 0 |
u16 width | u16 height | u16 1 | u16 mip count; then, for each mip: u32 pitch | u32 block rows |
u32 size | u32 0 + data (linear, bytes swapped in pairs). Names live in section 0x4C9B9EB2 (e.g. crest_cm.Raster).
RX3l files (PC, little-endian; FIFA 14 face packs) have the same layout with plain (unswapped) DXT data.
"""
import io
import struct

from PIL import Image

TEXTURE_SECTION, NAMES_SECTION = 0x7A0B60DA, 0x4C9B9EB2
DDS_FOURCC = {0: b'DXT1', 1: b'DXT3', 2: b'DXT5'}  # 1 = DXT3 (explicit 4-bit alpha), confirmed in game


def swap16(b):
    a = bytearray(len(b))
    a[0::2] = b[1::2]
    a[1::2] = b[0::2]
    return bytes(a)


def _endian(d):
    return '<' if d[:4] == b'RX3l' else '>'


def _sections(d):
    e = _endian(d)
    n = struct.unpack(e + 'I', d[12:16])[0]
    for i in range(n):
        yield struct.unpack(e + 'IIII', d[16 + 16 * i:32 + 16 * i])


def names(d):
    e = _endian(d)
    for type_, off, _, _ in _sections(d):
        if type_ == NAMES_SECTION:
            count = struct.unpack(e + 'I', d[off + 4:off + 8])[0]
            p, out = off + 16, []
            for _ in range(count):
                length = struct.unpack(e + 'I', d[p + 4:p + 8])[0]
                out.append(d[p + 8:p + 8 + length].split(b'\0')[0].decode().replace('.Raster', ''))
                p += 8 + length
            return out
    return []


def textures(d):
    e = _endian(d)
    out = []
    for type_, off, size, _ in _sections(d):
        if type_ != TEXTURE_SECTION:
            continue
        _, _, fmt, _, _, w, h, _, mips = struct.unpack(e + 'IBBBBHHHH', d[off:off + 16])
        levels, q = [], off + 16
        for m in range(mips):
            _, _, mip_size, _ = struct.unpack(e + 'IIII', d[q:q + 16])
            levels.append((q + 16, mip_size, max(1, w >> m), max(1, h >> m)))
            q += 16 + mip_size
        out.append(dict(off=off, size=size, fmt=fmt, w=w, h=h, mips=mips, levels=levels))
    for t, name in zip(out, names(d)):
        t['name'] = name
    return out


def by_name(d, name):
    for t in textures(d):
        if t.get('name') == name:
            return t
    raise KeyError(name)


def to_image(d, t, level=0):
    q, n, w, h = t['levels'][level]
    raw = d[q:q + n]
    little = _endian(d) == '<'
    if t['fmt'] in DDS_FOURCC:
        swapped = raw if little else swap16(raw)
        bw, bh = max(4, w), max(4, h)
        hdr = (b'DDS ' + struct.pack('<7I', 124, 0x1007, bh, bw, len(swapped), 0, 1) + b'\0' * 44 +
               struct.pack('<2I4s5I', 32, 4, DDS_FOURCC[t['fmt']], 0, 0, 0, 0, 0) + struct.pack('<5I', 0x1000, 0, 0, 0, 0))
        return Image.open(io.BytesIO(hdr + swapped)).crop((0, 0, w, h))
    return Image.frombytes('RGBA', (w, h), raw[:w * h * 4], 'raw', 'BGRA' if little else 'ARGB')


def _encode(img, t, w, h, bg=None):
    if t['fmt'] == 3:
        r, g, b, a = img.convert('RGBA').resize((w, h), Image.LANCZOS).split()
        return Image.merge('RGBA', (a, r, g, b)).tobytes()  # A R G B order
    im = img.convert('RGBA').resize((max(4, w), max(4, h)), Image.LANCZOS)
    if bg is not None:  # fixed color for fully transparent pixels (Pillow's resize zeroes their color)
        a = im.split()[3]
        im = Image.composite(im.convert('RGB'), Image.new('RGB', im.size, bg),
                             a.point(lambda v: 255 if v else 0)).convert('RGBA')
        im.putalpha(a)
    buf = io.BytesIO()
    im.save(buf, format='DDS', pixel_format=DDS_FOURCC[t['fmt']].decode())
    return swap16(bytes(buf.getvalue()[128:]))


def set_image(d, t, img, bg=None):
    """Writes img (PIL) into every mip of texture t (d = bytearray). bg = RGB of transparent pixels."""
    for q, n, w, h in t['levels']:
        b = _encode(img, t, w, h, bg)
        d[q:q + n] = b[:n].ljust(n, b'\0')


def set_image_dxt1(d, t, img):
    """Like set_image for a DXT1 texture, encoded with fsmod.dxt (sharper edges than Pillow's encoder)."""
    from . import dxt
    if t['fmt'] != 0:
        raise ValueError('not a DXT1 texture')
    src = img.convert('RGB')
    for q, n, w, h in t['levels']:
        b = swap16(dxt.encode(src.resize((max(4, w), max(4, h)), Image.LANCZOS)))
        d[q:q + n] = b[:n].ljust(n, b'\0')


def fill_solid(d, t, rgb):
    """Solid color in every mip (DXT1/DXT3 with identical blocks: lossless)."""
    r, g, b = rgb
    c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    if t['fmt'] == 0:
        block = swap16(struct.pack('<HHI', c, c, 0))
    elif t['fmt'] == 1:
        block = swap16(struct.pack('<BB6sHHI', 255, 255, b'\0' * 6, c, c, 0))
    else:
        return set_image(d, t, Image.new('RGBA', (t['w'], t['h']), (r, g, b, 255)))
    for q, n, _, _ in t['levels']:
        d[q:q + n] = block * (n // len(block))
