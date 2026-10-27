"""Image clean-up before DXT5 compression (menu crests, player photos).

DXT5 stores each 4x4 block with two colors (and their blends) plus an alpha ramp. Two things in cut-out images
(e.g. a photo with the background removed) turn into visible dots/halos around the subject:
  - nearly invisible pixels (alpha 1..ALPHA_FLOOR) left by the cut-out tool;
  - the color under transparent pixels: black after a Pillow resize (premultiplied alpha), so blocks on the
    border mix the subject's colors with black.
clean() drops the nearly invisible pixels and gives every transparent pixel the color of the nearest visible
ones ("edge bleeding"), so the border blocks only hold colors of the subject. The visible image does not change.
"""
from PIL import Image, ImageFilter

ALPHA_FLOOR = 24
BLEED_RADII = (64, 32, 16, 8, 4, 2, 1)  # coarse to fine: the closest visible color wins


def clean(img):
    """RGBA copy of img ready for DXT5: alpha below ALPHA_FLOOR -> 0, transparent pixels filled with nearby color."""
    img = img.convert('RGBA')
    alpha = img.getchannel('A').point(lambda a: 0 if a < ALPHA_FLOOR else a)
    visible = alpha.point(lambda a: 255 if a else 0)
    if not visible.getbbox():
        return img
    solid = img.copy()
    solid.putalpha(visible)
    filled = Image.new('RGB', img.size)
    for radius in BLEED_RADII:
        # premultiplied blur = average color of the visible pixels around each pixel
        blurred = solid.convert('RGBa').filter(ImageFilter.GaussianBlur(radius)).convert('RGBA')
        filled.paste(blurred.convert('RGB'), mask=blurred.getchannel('A').point(lambda a: 255 if a else 0))
    filled.paste(img.convert('RGB'), mask=visible)
    filled.putalpha(alpha)
    return filled
