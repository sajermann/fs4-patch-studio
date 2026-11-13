"""Name and numbers printed on a kit, for the 3D preview (the game draws them itself at run time).

Where: the position table of the kit rx3 (fsmod.kit._positions: u0, v0, u1, v1 per rectangle; u0 > u1 / v0 > v1 =
the rectangle is mirrored, as the back of the jersey is upside down in the texture). A real kit built by the app uses
its own table (RealKit.positions, e.g. a FIFA 14 kit's) or kit.REAL_POSITIONS; an original team's own kit has its own
table.
What: the numbers are 10 textures per font and color (data/sceneassets/kitnumbers/kitnumbers_<font>_<color>.rx3,
one 128x128 image per digit); the name is drawn with a TrueType font (data/sceneassets/jerseyfonts/font_<n>.ttf) in
the RGB name color, straight (jerseynamelayouttype 0) or in an arc (1, seen in game: the middle of the name highest,
the letters turned along the curve). The arc is an approximation (the game's own maths is not known): a circle around
name_arccenter whose radius is ARC_RADIUS_FACTOR times its distance to name_arctangent, each letter kept as wide as
when straight.
Font numbers, case and layout come from the team's teamkits row (numberfonttype, shortsnumberfonttype,
jerseynamefonttype, jerseybacknamefontcase, jerseynamelayouttype).
"""
import io
import math
import struct
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import chunk, kit, rx3tex

NUMBERS = 'data/sceneassets/kitnumbers/kitnumbers_{}_{}.rx3'
NAME_FONT = 'data/sceneassets/jerseyfonts/font_{}.ttf'
TRACKING = 0.2  # gap between the letters, in average letter widths
MAX_STRETCH = 1.8  # a short name is widened up to this much to fill the rectangle (the game does it, Barcelona)
# the arc's radius = this times the distance name_arccenter -> name_arctangent: measured on a game print (Real Madrid,
# RONALDO, layout 1, 12/11/2026), the game's bend is about half of what the plain distance gives
ARC_RADIUS_FACTOR = 2.0


def positions(sources, teamid=None, kind=0, table=None, show_name=True):
    """{rectangle name: (u0, v0, u1, v1)} of a kit: the game's own kit of teamid, or a built real kit's table (teamid
    None: RealKit.positions `table` or kit.REAL_POSITIONS, the name rectangles zeroed without a name; kit.position_table).
    'team' (crest) appears twice (jersey, shorts): only the jersey one is kept."""
    if teamid is None:
        return dict(reversed(kit.position_table(table, show_name)))
    d = bytearray(chunk.decode(sources.read_entry(kit.kit_name(teamid, kind))[2]))
    out = {}
    for name, p in kit._positions(d):
        out.setdefault(name, struct.unpack('>4f', d[p:p + 16]))
    return out


@lru_cache(maxsize=32)
def digits(sources, font, color):
    """The 10 digit images (RGBA) of a number font and palette color, or None when the game has no such file."""
    entry = sources.read_entry(NUMBERS.format(font, color))
    if not entry:
        return None
    d = chunk.decode(entry[2])
    return [rx3tex.to_image(d, t).convert('RGBA') for t in rx3tex.textures(d)[:10]]


@lru_cache(maxsize=8)
def _font_bytes(sources, font):
    entry = sources.read_entry(NAME_FONT.format(font))
    return chunk.decode(entry[2]) if entry else None


def _box(rect, size):
    """Pixel box (left, top, right, bottom) and mirroring (flip_x, flip_y) of a UV rectangle on a texture."""
    w, h = size
    u0, v0, u1, v1 = rect
    box = (round(min(u0, u1) * w), round(min(v0, v1) * h), round(max(u0, u1) * w), round(max(v0, v1) * h))
    return box, u0 > u1, v0 > v1


def _paste(img, layer, box, flip_x, flip_y):
    if flip_x:
        layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_y:
        layer = layer.transpose(Image.FLIP_TOP_BOTTOM)
    img.alpha_composite(layer.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS), box[:2])


def draw_number(img, rect, number, glyphs):
    """Draws a 1-2 digit number in a UV rectangle: each digit takes half of its width (one digit is centered)."""
    box, flip_x, flip_y = _box(rect, img.size)
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 2 or h < 2:
        return
    text = str(number)[-2:]
    cell = 128
    layer = Image.new('RGBA', (cell * 2, cell), (0, 0, 0, 0))
    x = (2 - len(text)) * cell // 2
    for ch in text:
        layer.alpha_composite(glyphs[int(ch)], (x, 0))
        x += cell
    _paste(img, layer, box, flip_x, flip_y)


def draw_name(img, rect, name, font_data, color, arc=None):
    """Draws a name in a UV rectangle, letters as tall as the rectangle, widened to fill its width like the game does
    (up to MAX_STRETCH; a long name is narrowed to fit). arc = (name_arccenter, name_arctangent) rectangles: the name
    bends around the center (layout 1); None or a zero radius = straight."""
    box, flip_x, flip_y = _box(rect, img.size)
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 2 or h < 2 or not name:
        return
    scale = 4  # drawn bigger, then reduced
    font = ImageFont.truetype(io.BytesIO(font_data), h * scale)
    top, bottom = font.getbbox(name)[1], font.getbbox(name)[3]
    widths = [font.getlength(c) for c in name]
    gap = TRACKING * sum(widths) / len(name)
    text_w = max(1, round(sum(widths) + gap * (len(name) - 1)))
    line = Image.new('RGBA', (text_w, bottom - top), (0, 0, 0, 0))
    draw = ImageDraw.Draw(line)
    x = 0.0
    spans = []  # each letter's columns in the line
    for c, cw in zip(name, widths):
        draw.text((x, -top), c, font=font, fill=(*color, 255))
        spans.append((x, x + cw))
        x += cw + gap
    fit_w = min(round(text_w * MAX_STRETCH), w * scale)
    line = line.resize((fit_w, h * scale), Image.LANCZOS)
    radius = _arc_radius(arc, img.size) * scale if arc else 0
    if radius < h * scale:  # straight (or a radius too small to bend around)
        layer = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
        layer.alpha_composite(line, ((layer.width - line.width) // 2, 0))
        _paste(img, layer, box, flip_x, flip_y)
        return
    _paste_arc(img, line, [(a * fit_w / text_w, b * fit_w / text_w) for a, b in spans], radius, box, w * scale,
               h * scale, flip_x, flip_y)


def _arc_radius(arc, size):
    """Radius of the circle the name bends around, in pixels (ARC_RADIUS_FACTOR x name_arccenter -> name_arctangent),
    0 when unknown."""
    center, tangent = arc
    if not any(center) or not any(tangent):
        return 0
    return ARC_RADIUS_FACTOR * math.hypot((tangent[0] - center[0]) * size[0], (tangent[1] - center[1]) * size[1])


def _paste_arc(img, line, spans, radius, box, w, h, flip_x, flip_y):
    """The name bent on a circle of `radius` (upright: the middle highest, the ends lower and turned outwards): each
    letter keeps its width as arc length around the middle of the line. The layer grows down by the bend, past the
    rectangle (toward the number), like the game's."""
    mid = line.width / 2
    letters = []
    lowest = 0.0
    for a, b in spans:
        cx = (a + b) / 2 - mid
        theta = cx / radius
        x = radius * math.sin(theta)
        drop = radius * (1 - math.cos(theta))
        piece = line.crop((max(0, math.floor(a)), 0, min(line.width, math.ceil(b)), line.height))
        piece = piece.rotate(-math.degrees(theta), resample=Image.BICUBIC, expand=True)
        letters.append((piece, x, drop))
        lowest = max(lowest, drop + piece.height / 2)
    extra = max(0, math.ceil(lowest + h / 2 - h))
    layer = Image.new('RGBA', (w, h + extra), (0, 0, 0, 0))
    for piece, x, drop in letters:
        px = round(w / 2 + x - piece.width / 2)
        py = round(h / 2 + drop - piece.height / 2)
        layer.alpha_composite(piece, (max(0, px), max(0, py)),
                              (max(0, -px), max(0, -py)))
    scale = (box[3] - box[1]) / h  # layer pixels -> texture pixels
    grow = round(extra * scale)
    # upright "down" (toward the number) is the rectangle's v0 side when it is mirrored, its v1 side otherwise
    bigger = (box[0], box[1] - grow, box[2], box[3]) if flip_y else (box[0], box[1], box[2], box[3] + grow)
    _paste(img, layer, bigger, flip_x, flip_y)


def print_kit(img, part, sources, *, number=None, name=None, rects, number_font, shorts_number_font, name_font,
              number_color, shorts_number_color, name_color, name_case=0, front_number=False,
              shorts_number=False, name_layout=0, name_font_data=None, number_glyphs=None, shorts_number_glyphs=None):
    """Draws the name and numbers of one player on a kit texture (part 'jersey' or 'shorts'; img RGBA, edited).
    name_font_data / number_glyphs / shorts_number_glyphs: the kit's own fonts (fsmod.kitfonts), used instead of the
    game's font numbers."""
    if part == 'jersey':
        glyphs = number_glyphs or (digits(sources, number_font, number_color) if number is not None else None)
        if glyphs:
            draw_number(img, rects['numberback'], number, glyphs)
            if front_number and 'numberfront' in rects:
                draw_number(img, rects['numberfront'], number, glyphs)
        font = (name_font_data or _font_bytes(sources, name_font)) if name else None
        if font:
            arc = (rects.get('name_arccenter'), rects.get('name_arctangent')) if name_layout == 1 else None
            draw_name(img, rects['name'], name.upper() if name_case == 0 else name, font, tuple(name_color),
                      arc if arc and all(arc) else None)
    elif shorts_number and number is not None and 'number' in rects:
        glyphs = shorts_number_glyphs or digits(sources, shorts_number_font, shorts_number_color)
        if glyphs:
            draw_number(img, rects['number'], number, glyphs)
    return img
