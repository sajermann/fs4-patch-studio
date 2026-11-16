"""Fonts of the game's menus (Project.game_patches.ui_fonts): a TrueType file of the user's in place of one of the game's.

The menus draw their text with plain TrueType files in data0.big (data/ui/fonts/*.ttf). The UI loads only the files
listed in data/ui/fonts/fonts.txt (SLOTS) and registers each one by its internal name ('name' table); the screens ask
for those names. So a replacement:
  - keeps the 'name' table of the font it replaces (a file with its own name is ignored: the screens fall back to
    another font; validated in game, 16/11/2026),
  - is drawn the same size and in the same place as the original: the game's fonts put the ascender at the height of
    the capitals, so a common font (ascender well above them) would sit lower and overlap the line above. The
    replacement gets the original's capital height (by changing its units per em, which scales every glyph) and the
    original's vertical metrics (hhea, OS/2 typo), in its new units. Widths are the font's own: a wider font than
    the original makes long texts shrink to fit their boxes (the screens do that), so a condensed font fits the
    condensed slots best,
  - loses the tables that would be wrong after that (hdmx/VDMX/LTSH: precomputed per pixel size; DSIG) and the
    variation tables (a variable font becomes its default instance),
  - goes as a loose file Game/data/ui/fonts/<file> (chunkzip) with its record zeroed in data0.bh, like every
    replaced entry (builder.write_patch_loose).
Only TrueType outlines ('glyf') are accepted: the game's fonts are all TrueType and CFF ones were never tried.
"""
import io
import struct

from PIL import Image, ImageDraw, ImageFont

from . import chunk

ARCHIVE = 'data0.big'
FONTS_DIR = 'data/ui/fonts/'
# slot (Project.game_patches.ui_fonts key) -> file in data0, in fonts.txt order (only these are loaded)
SLOTS = {
    'body': 'fs4_body.ttf',
    'cn_bold': 'fs4_cn_bold.ttf',
    'cn_regular': 'fs4_cn_regular.ttf',
    'header': 'fs4_header.ttf',
    'handwritten': 'fs4_handwritten.ttf',
    'courier': 'fs4_courier.ttf',
    'ea05_body': 'ea05_body.ttf',
}
# characters the game's texts use (Portuguese and the other languages of the menus); missing ones only warn
REQUIRED_CHARS = ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
                  'ÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüç.,:;!?%/()-+')
DROPPED_TABLES = {b'hdmx', b'VDMX', b'LTSH', b'DSIG', b'fvar', b'gvar', b'avar', b'cvar', b'HVAR', b'VVAR', b'MVAR',
                  b'STAT'}
MIN_UPM, MAX_UPM = 16, 16384
PREVIEW_TEXT = 'JOGAR NA RUA  Ação 5 contra 5'


class UiFontError(ValueError):
    """A file that cannot be a menu font; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def entry_name(slot):
    return FONTS_DIR + SLOTS[slot]


def decode(data):
    """File bytes as stored (chunk-compressed, as in the game's archives, or plain)."""
    return chunk.decode(data) if data[:5] == b'chunk' else data


def tables(data):
    """(sfnt version, {tag: bytes}) of a TrueType file."""
    if len(data) < 12:
        raise UiFontError('ui_font_unreadable')
    version = data[:4]
    n = struct.unpack('>H', data[4:6])[0]
    if len(data) < 12 + 16 * n:
        raise UiFontError('ui_font_unreadable')
    out = {}
    for i in range(n):
        tag = data[12 + i * 16:16 + i * 16]
        offset, length = struct.unpack('>II', data[20 + i * 16:28 + i * 16])
        if offset + length > len(data):
            raise UiFontError('ui_font_unreadable', tag.decode('latin1'))
        out[tag] = data[offset:offset + length]
    return version, out


def _checksum(data):
    data += b'\0' * (-len(data) % 4)
    return sum(struct.unpack(f'>{len(data) // 4}I', data)) & 0xFFFFFFFF


def build(version, font_tables):
    """TrueType file from {tag: bytes}: tables sorted and 4-byte aligned, their checksums and the head's
    checkSumAdjustment."""
    font_tables = dict(font_tables)
    font_tables[b'head'] = font_tables[b'head'][:8] + bytes(4) + font_tables[b'head'][12:]
    tags = sorted(font_tables)
    n = len(tags)
    power = 1 << (n.bit_length() - 1)
    out = bytearray(version + struct.pack('>HHHH', n, power * 16, power.bit_length() - 1, n * 16 - power * 16))
    position, body, head_at = 12 + 16 * n, bytearray(), 0
    for tag in tags:
        data = font_tables[tag]
        if tag == b'head':
            head_at = position + len(body)
        out += tag + struct.pack('>III', _checksum(data), position + len(body), len(data))
        body += data + b'\0' * (-len(data) % 4)
    out += body
    out[head_at + 8:head_at + 12] = struct.pack('>I', (0xB1B0AFBA - _checksum(bytes(out))) & 0xFFFFFFFF)
    return bytes(out)


def _units_per_em(font_tables):
    return struct.unpack('>H', font_tables[b'head'][18:20])[0]


def _cap_height(data):
    """Height of the capital H as a fraction of the em (drawn at 1000 px), or None without an H."""
    try:
        font = ImageFont.truetype(io.BytesIO(data), 1000)
        box = font.getbbox('H')
    except Exception:  # noqa: BLE001
        return None
    height = box[3] - box[1]
    return height / 1000 if height > 0 else None


def font_name(data):
    """'Family Style' of a font file, or None."""
    try:
        return ' '.join(ImageFont.truetype(io.BytesIO(decode(data)), 12).getname()).strip() or None
    except Exception:  # noqa: BLE001
        return None


def check(data):
    """Raises UiFontError unless data is a TrueType font the game can use (TrueType outlines, readable)."""
    data = decode(data)
    if data[:4] == b'OTTO':
        raise UiFontError('ui_font_not_truetype')
    if data[:4] not in (b'\0\1\0\0', b'true'):
        raise UiFontError('ui_font_unreadable')
    _, font_tables = tables(data)
    if b'glyf' not in font_tables:
        raise UiFontError('ui_font_not_truetype')
    for tag in (b'head', b'hhea', b'name', b'cmap', b'maxp', b'hmtx', b'loca'):
        if tag not in font_tables:
            raise UiFontError('ui_font_unreadable', tag.decode())
    if font_name(data) is None:
        raise UiFontError('ui_font_unreadable')


def characters(data, wanted):
    """Characters of `wanted` the font maps to a real glyph (not glyph 0) in a cmap subtable of format 4 or 12."""
    cmap = tables(decode(data))[1].get(b'cmap', b'')
    found = set()
    if len(cmap) < 4:
        return found
    codes = {ord(c) for c in wanted}
    for i in range(struct.unpack('>H', cmap[2:4])[0]):
        offset = struct.unpack('>I', cmap[8 + i * 8:12 + i * 8])[0]
        sub = cmap[offset:]
        fmt = struct.unpack('>H', sub[:2])[0]
        if fmt == 4:
            count = struct.unpack('>H', sub[6:8])[0] // 2
            ends = struct.unpack(f'>{count}H', sub[14:14 + 2 * count])
            starts = struct.unpack(f'>{count}H', sub[16 + 2 * count:16 + 4 * count])
            deltas = struct.unpack(f'>{count}h', sub[16 + 4 * count:16 + 6 * count])
            range_at = 16 + 6 * count
            ranges = struct.unpack(f'>{count}H', sub[range_at:range_at + 2 * count])
            for code in codes:
                for k, (start, end) in enumerate(zip(starts, ends)):
                    if not start <= code <= end:
                        continue
                    if ranges[k] == 0:
                        glyph = (code + deltas[k]) & 0xFFFF
                    else:
                        at = range_at + 2 * k + ranges[k] + 2 * (code - start)
                        glyph = struct.unpack('>H', sub[at:at + 2])[0]
                        glyph = (glyph + deltas[k]) & 0xFFFF if glyph else 0
                    if glyph:
                        found.add(chr(code))
                    break
        elif fmt == 12:
            for g in range(struct.unpack('>I', sub[12:16])[0]):
                start, end, first = struct.unpack('>III', sub[16 + g * 12:28 + g * 12])
                found.update(chr(c) for c in codes if start <= c <= end and first + c - start)
    return found


def missing_chars(data):
    """Characters of REQUIRED_CHARS the font has no glyph for."""
    try:
        have = characters(data, REQUIRED_CHARS)
    except Exception:  # noqa: BLE001
        return REQUIRED_CHARS
    return ''.join(c for c in REQUIRED_CHARS if c not in have)


def convert(original, new):
    """The game's font file for a slot: the outlines of `new` answering to the names of `original` (both plain
    TrueType bytes), at the original's capital height and vertical metrics."""
    check(new)
    new = decode(new)
    version, font_tables = tables(new)
    _, own = tables(original)
    font_tables = {tag: data for tag, data in font_tables.items() if tag not in DROPPED_TABLES}
    font_tables[b'name'] = own[b'name']
    upm, own_upm = _units_per_em(font_tables), _units_per_em(own)
    ascender, descender, gap = struct.unpack('>hhh', own[b'hhea'][4:10])
    cap, own_cap = _cap_height(new), _cap_height(original)
    if own_cap and ascender > 0:
        own_cap = min(own_cap, ascender / own_upm)  # the handwritten font's capitals go above its own line
    new_upm = upm
    if cap and own_cap:
        new_upm = max(MIN_UPM, min(MAX_UPM, round(upm * cap / own_cap)))
    head = bytearray(font_tables[b'head'])
    head[18:20] = struct.pack('>H', new_upm)
    font_tables[b'head'] = bytes(head)

    def scaled(value):
        return round(value * new_upm / own_upm)

    hhea = bytearray(font_tables[b'hhea'])
    hhea[4:10] = struct.pack('>hhh', scaled(ascender), scaled(descender), scaled(gap))
    font_tables[b'hhea'] = bytes(hhea)
    os2 = font_tables.get(b'OS/2')
    if os2 is not None and len(os2) >= 74:
        os2 = bytearray(os2)
        os2[68:74] = struct.pack('>hhh', scaled(ascender), scaled(descender), scaled(gap))
        font_tables[b'OS/2'] = bytes(os2)
    return build(version, font_tables)


def original(game, slot):
    """The game's font file of a slot (plain TrueType bytes)."""
    entry = game.read_entry(entry_name(slot))
    if not entry:
        raise UiFontError('ui_font_original_missing', slot)
    return decode(entry[2])


def entries(game, ui_fonts, read):
    """{(ARCHIVE, entry): chunkzip} of the slots with a file (model.GamePatches.ui_fonts; read(path) -> bytes)."""
    out = {}
    for slot, choice in ui_fonts.items():
        if slot not in SLOTS or not choice.file:
            continue
        out[ARCHIVE, entry_name(slot)] = chunk.chunkzip(convert(original(game, slot), read(choice.file)))
    return out


def preview(game, slot, data=None, size=44):
    """PNG of PREVIEW_TEXT in a slot's font: the uploaded file converted as the patch does (data), else the
    game's. Dark text on a light background, the original's line height."""
    own = original(game, slot)
    font_data = convert(own, data) if data is not None else own
    font = ImageFont.truetype(io.BytesIO(font_data), size)
    width = int(font.getlength(PREVIEW_TEXT)) + size
    img = Image.new('RGBA', (width, int(size * 1.6)), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((size // 2, int(size * 0.3)), PREVIEW_TEXT, font=font, fill=(20, 20, 20, 255))
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
