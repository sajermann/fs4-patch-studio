"""A real kit's own fonts: files that come with the kit (e.g. a FIFA 14 club font the game does not have).

How the game prints a kit (data0: data/fifarna/lua/assets/player.lua): the name with
data/sceneassets/jerseyfonts/font_<teamkits.jerseynamefonttype>.ttf and the numbers with
data/sceneassets/kitnumbers/kitnumbers_<numberfonttype>_<numbercolor>.rx3 (10 textures, one per digit, the color
painted in). New font numbers work as loose files under Game/data/... (validated in game: name font 25, number font
31). The game has name fonts 0-24 and number fonts 0-30, and the fields are 8 bits.

A RealKit with name_font / number_font / shorts_number_font = KIT uses its own file (RealKit.name_font_file,
number_font_file, shorts_number_font_file). The build gives each different file a free font number
(assign_font_ids: name fonts NAME_IDS, number fonts NUMBER_IDS) and writes:
  name     the .ttf as it is, as font_<id>.ttf
  numbers  kitnumbers_<id>_<color>.rx3 with the file's digits for the kit's color (its own colors: a club font has
           them painted in), in the game's layout (number_file)
"""
import hashlib
import io

import numpy as np
from PIL import Image, ImageFont

from . import chunk, rx3tex

KIT = 'kit'  # RealKit font field value: the kit's own font file
NAME_IDS = range(25, 256)  # free jerseynamefonttype numbers (the game has 0-24)
# free numberfonttype numbers (the game has 0-30); two digits, as the game file a new one is written into
NUMBER_IDS = range(31, 100)
NAME_FILE = 'data/sceneassets/jerseyfonts/font_{}.ttf'
NUMBERS_FILE = 'data/sceneassets/kitnumbers/kitnumbers_{}_{}.rx3'
TEMPLATE_FONT = 16  # game number font whose file (same color) holds a converted one: two-digit names
DIGITS = 10
# number font with the digits in every palette color: what a kit falls back to when its own font has no number
# and the teamkits row's font lacks the kit's color (the numbers always show)
FALLBACK_NUMBER_FONT = 1
# mean difference of the 10 digits (64x64 RGBA, 0-255) under which a numbers file is the game's own font: FIFA 14's
# copies of the game's fonts measure 1-9, other fonts 24 and up (measured 12/11/2026, colors 1 and 5)
SAME_DIGITS = 15
FONT_PARTS = (('name_font', 'name_font_file'), ('number_font', 'number_font_file'),
              ('shorts_number_font', 'shorts_number_font_file'))  # RealKit choice -> its file field


class FontError(ValueError):
    """A file that is not a usable font; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def decode(data):
    """File bytes as stored (a FIFA pack's chunk-compressed file or plain)."""
    try:
        return chunk.decode(data)
    except Exception:  # noqa: BLE001 (not chunk-compressed)
        return data


def check_name_font(data):
    """Raises FontError unless data is a TrueType/OpenType font."""
    if decode(data)[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
        raise FontError('font_not_ttf')


def check_number_font(data):
    """Raises FontError unless data is a kit numbers file (RX3 with the 10 digit textures)."""
    d = decode(data)
    try:
        textures = rx3tex.textures(d) if d[:4] in (b'RX3l', b'RX3b') else []
    except Exception:  # noqa: BLE001
        textures = []
    if len(textures) < DIGITS:
        raise FontError('font_not_numbers')


def number_file(game, data, font, color):
    """kitnumbers_<font>_<color>.rx3 for the game (bytes, uncompressed) from a numbers file of any layout: its 10
    digits written into the game's own file of TEMPLATE_FONT in that color (raw blocks when the format and size are
    the same, byte pairs swapped for a little-endian file; otherwise the digit is redrawn), texture names renamed."""
    d = bytearray(chunk.decode(game.read_entry(NUMBERS_FILE.format(TEMPLATE_FONT, color))[2]))
    src = decode(data)
    mine, theirs = rx3tex.textures(d), rx3tex.textures(src)
    if len(theirs) < DIGITS:
        raise FontError('font_not_numbers')
    little = src[:4] == b'RX3l'
    for a, b in zip(mine[:DIGITS], theirs[:DIGITS]):
        same = (a['fmt'], a['w'], a['h']) == (b['fmt'], b['w'], b['h'])
        levels = list(zip(a['levels'], b['levels']))
        if same and all(n == n2 for (_, n, _, _), (_, n2, _, _) in levels):
            for (q, n, _, _), (q2, _, _, _) in levels:
                block = bytes(src[q2:q2 + n])
                d[q:q + n] = rx3tex.swap16(block) if little else block
        else:
            rx3tex.set_image(d, a, rx3tex.to_image(src, b).convert('RGBA'))
    old = f'numbers_{TEMPLATE_FONT}_{color}_'.encode()
    new = f'numbers_{font}_{color}_'.encode()
    if len(old) != len(new):
        raise ValueError(f'number font {font}: not two digits')
    return bytes(d).replace(old, new)


def name_file(data):
    """font_<id>.ttf for the game (bytes, uncompressed)."""
    return decode(data)


def digest(data):
    return hashlib.sha1(decode(data)).hexdigest()


def font_choice(real, field):
    """What a RealKit field (name_font, number_font, shorts_number_font) asks for: an int (a game font), KIT (its own
    file) or None (the teamkits row's)."""
    return getattr(real, field)


def font_key(real, field, file_digest):
    """Key of a kit's own font file in assign_font_ids: ('name', SHA-1) or ('number', SHA-1, color it is used in)."""
    if field == 'name_font':
        return 'name', file_digest
    return 'number', file_digest, real.number_color if field == 'number_font' else real.shorts_number_color


def assign_font_ids(kits, read):
    """{font_key: font number} for the kits' own fonts in use (kits = RealKits, read(project path) -> bytes), in the
    order met. A name font takes a number of its own. A numbers file only takes its color under a number (the game
    reads kitnumbers_<number>_<color>), so different fonts share a number in different colors: the first number whose
    color is still free. A file left without a free number maps to None: its kit keeps a game font (the name and
    numbers still show, in a generic font; the validation warns, real_kit_font_no_slot)."""
    out = {}
    names = iter(NAME_IDS)
    taken = {}  # number font -> colors in use
    for real in kits:
        for field, file_field in FONT_PARTS:
            path = getattr(real, file_field)
            if getattr(real, field) != KIT or not path:
                continue
            key = font_key(real, field, digest(read(path)))
            if key in out:
                continue
            if field == 'name_font':
                out[key] = next(names, None)
            else:
                color = key[2]
                out[key] = next((n for n in NUMBER_IDS if color not in taken.get(n, ())), None)
                if out[key] is not None:
                    taken.setdefault(out[key], set()).add(color)
    return out


def without_slot(kits, read):
    """[(real kit, font field)] of the kits' own fonts left without a free number (assign_font_ids)."""
    ids = assign_font_ids(kits, read)
    out = []
    for real in kits:
        for field, file_field in FONT_PARTS:
            path = getattr(real, file_field)
            if getattr(real, field) == KIT and path and ids.get(font_key(real, field, digest(read(path)))) is None:
                out.append((real, field))
    return out


def preview_digits(data):
    """The 10 digit images (RGBA) of a numbers file, for the 3D preview."""
    d = decode(data)
    textures = rx3tex.textures(d)
    if len(textures) < DIGITS:
        raise FontError('font_not_numbers')
    return [rx3tex.to_image(d, t).convert('RGBA').resize((128, 128), Image.LANCZOS) for t in textures[:DIGITS]]


def _font_name(data):
    try:
        return ImageFont.truetype(io.BytesIO(data), 12).getname()
    except Exception:  # noqa: BLE001
        return None


def same_name_font(game, font, data):
    """The game's name font `font` is this .ttf: the same file, or the same font name and style (a newer version of
    a font, e.g. BarcelonaFont16 for BarcelonaFont, is another font)."""
    entry = game.read_entry(NAME_FILE.format(font)) if isinstance(font, int) else None
    if not entry:
        return False
    mine, theirs = decode(entry[2]), decode(data)
    return mine == theirs or (_font_name(mine) is not None and _font_name(mine) == _font_name(theirs))


def same_number_font(game, font, color, data):
    """The game's number font `font` in `color` draws the same digits as this numbers file (SAME_DIGITS)."""
    entry = game.read_entry(NUMBERS_FILE.format(font, color)) if isinstance(font, int) else None
    if not entry:
        return False
    try:
        mine = np.stack([np.asarray(d.resize((64, 64)), dtype=np.float32) for d in preview_digits(entry[2])])
        theirs = np.stack([np.asarray(d.resize((64, 64)), dtype=np.float32) for d in preview_digits(data)])
    except (FontError, ValueError, KeyError):
        return False
    return float(np.abs(mine - theirs).mean()) < SAME_DIGITS


def settle(game, real, read):
    """For a RealKit that comes with font files and the font numbers of another game (a zip from another tool): the
    game's own font when it is the same as the file (the file is dropped: no free number spent), else the kit's own
    file (KIT). read(project path) -> bytes. Edits real."""
    for field, file_field in FONT_PARTS:
        path, value = getattr(real, file_field), getattr(real, field)
        if not path or value == KIT:
            continue
        data = read(path)
        if field == 'name_font':
            same = same_name_font(game, value, data)
        else:
            color = real.number_color if field == 'number_font' else real.shorts_number_color
            same = same_number_font(game, value, color, data)
        if same:
            setattr(real, file_field, None)
            if field == 'name_font':
                real.name_font_name = None
        else:
            setattr(real, field, KIT)
