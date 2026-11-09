"""Ready thumbnails of the game's player creator (data1.big), offered for the generic appearance codes.

The files are 256x128, but the picture only takes the top left 145x100 (the rest is transparent) with the subject in
its middle: the image is the square BOX of it. The creator's screens use them with its own numbers, so the codes are read
like this:
  hairtypecode         hair/hair_<code>_<hair color>       (126 styles by 12 colors; hairs 27, 50 and 213 have none)
  haircolorcode        hair_color/<code>
  facialhairtypecode   facialhair/fhair_<code>_<beard color>
  facialhaircolorcode  facial_hair_color/<code>
  eyecolorcode         eye_color/<code - 1>                (the creator counts 0-6, the players table 1-7)
  eyebrowcode          eyebrows/eyebrows_0_0_<code>_0      (head 0, color 0, shape 0; the creator's 18 eyebrows are these
                                                            3 kinds by 6 shapes)
  skintonecode         headshape/head_0_<code>             (the creator's head shape pictures: a bald head in each
                                                            skin tone; they exist for exactly the 7 tones generics use,
                                                            2, 4, 5, 6, 8, 9 and 10, by 9 shapes)
"""
import io

from PIL import Image

from . import chunk

FOLDER = 'data/ui/imgassets/'
BOX = (22, 0, 122, 100)
SIZE = 128
_NAMES = {
    'hairtypecode': lambda code, variant: f'hair/hair_{code}_{variant}',
    'haircolorcode': lambda code, variant: f'hair_color/{code}',
    'facialhairtypecode': lambda code, variant: f'facialhair/fhair_{code}_{variant}',
    'facialhaircolorcode': lambda code, variant: f'facial_hair_color/{code}',
    'eyecolorcode': lambda code, variant: f'eye_color/{code - 1}',
    'eyebrowcode': lambda code, variant: f'eyebrows/eyebrows_0_0_{code}_0',
    'skintonecode': lambda code, variant: f'headshape/head_0_{code}',
}
FIELDS = tuple(_NAMES)


def thumbnail(game, field, code, variant=0):
    """PIL image of an appearance code, or None when the game has none. variant: the color of a hair or beard style."""
    entry = game.read_entry(f'{FOLDER}{_NAMES[field](code, variant)}.dds')
    if entry is None:
        return None
    image = Image.open(io.BytesIO(chunk.decode(entry[2]))).convert('RGBA')
    return image.crop(BOX).resize((SIZE, SIZE), Image.LANCZOS)
