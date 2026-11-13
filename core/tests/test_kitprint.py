"""Name and numbers drawn on a kit for the 3D preview (fsmod.kitprint)."""
from PIL import Image, ImageChops

from fsmod import chunk, kit, kitprint, rx3tex

REAL_MADRID = 243  # layout 0 in the game; its kit table has an arc center and tangent


def back(game, **kw):
    d = chunk.decode(game.read_entry(kit.kit_name(REAL_MADRID, 0))[2])
    base = rx3tex.to_image(d, rx3tex.by_name(d, 'jersey_cm')).convert('RGBA')
    args = dict(number=7, name='Ronaldo', rects=kitprint.positions(game, REAL_MADRID, 0), number_font=19,
                shorts_number_font=19, name_font=20, number_color=1, shorts_number_color=1, name_color=(200, 170, 100))
    return kitprint.print_kit(base, 'jersey', game, **{**args, **kw})


def test_arc_bends_the_name_toward_the_number(game):
    rects = kitprint.positions(game, REAL_MADRID, 0)
    plain = back(game, name=None, number=None)
    straight = back(game, name_layout=0, number=None)
    arc = back(game, name_layout=1, number=None)
    assert straight.tobytes() != arc.tobytes()
    box, _, flip_y = kitprint._box(rects['name'], plain.size)

    def changed_rows(img):
        diff = ImageChops.difference(img.convert('RGB'), plain.convert('RGB')).convert('L')
        diff = diff.crop((box[0], 0, box[2], img.height)).point(lambda v: 255 if v > 40 else 0)
        return diff.getbbox()

    s, a = changed_rows(straight), changed_rows(arc)
    # the bent ends go past the rectangle toward the number (the mirrored back: lower v), the straight name does not
    if flip_y:
        assert a[1] < s[1]
    else:
        assert a[3] > s[3]


def test_no_arc_without_center_or_with_a_long_name(game):
    rects = dict(kitprint.positions(game, REAL_MADRID, 0))
    straight = back(game, name_layout=0)
    flat = dict(rects, name_arccenter=(0.0, 0.0, 0.0, 0.0))
    assert back(game, name_layout=1, rects=flat).tobytes() == straight.tobytes()
    long = back(game, name_layout=1, name='Cristiano Ronaldo dos Santos Aveiro')
    assert isinstance(long, Image.Image)
