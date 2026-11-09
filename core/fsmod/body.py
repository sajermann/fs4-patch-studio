"""bodytypecode = height class x build.

The game's 9 body types are 3 builds (lean, medium, stocky) for each of 3 height classes: 1-3 normal, 4-6 tall,
7-9 short (CreatePlayerBodyType_<n>; genplayers.ini: BODYTYPE_LEAN 1, REGULAR 2, STOCKY 3). The class limits come
from the game's own players (a few exceptions). In game the player's height comes from `height` alone; the body type
only changes the build. So the app lets the user pick the build and takes the class from the height.
"""
SHORT_UP_TO, TALL_FROM = 170, 185
BUILDS = ('lean', 'medium', 'stocky')
_CLASS_OFFSET = {'normal': 0, 'tall': 3, 'short': 6}


def height_class(height):
    """'short', 'normal' or 'tall'."""
    if height <= SHORT_UP_TO:
        return 'short'
    return 'tall' if height >= TALL_FROM else 'normal'


def codes(height):
    """The bodytypecode values that fit a height (lean, medium, stocky)."""
    first = _CLASS_OFFSET[height_class(height)] + 1
    return first, first + 1, first + 2


def build_of(code):
    """0 lean, 1 medium, 2 stocky."""
    return (max(code, 1) - 1) % 3


def fit(code, height):
    """The same build in the height class of `height`."""
    return codes(height)[build_of(code)]
