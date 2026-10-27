"""Player photos (the 2D head shown in menus): data/ui/imgassets/heads/p<playerid>.dds in 2dheads.big.

Each original entry is a single-chunk 'chunkzip' with a 128x128 DXT5 DDS (alpha, no mips): 128-byte header +
16,384 bytes of pixels + 8 trailing bytes. The app writes SIZE px (validated in game on ReStreet 2.x:
same size on screen, sharper); the bigger entry goes to the end of 2dheads.big (builder.write_patch).
New players: entries added to an archive are not found, but the game opens
d:/data/ui/imgassets/heads/p<playerid>.dds from disk when 2dheads.big has no such entry ⇒ the photo of a new
playerid is a loose file with the same bytes as an entry (validated in game).
"""
import io

from PIL import Image

from . import chunk, crest, imageprep

ORIGINAL_SIZE = 128
SIZE = ORIGINAL_SIZE * 2
PHOTOS_ARCHIVE = '2dheads.big'


def photo_name(playerid):
    return f'data/ui/imgassets/heads/p{playerid}.dds'


def prepare(img):
    """Square SIZE x SIZE RGBA: wide images are cropped at the center, tall ones keep the top (the face)."""
    img = img.convert('RGBA')
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    img = img.crop((left, 0, left + side, side))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def photo_file(game, img):
    """Bytes of a photo entry (any original photo gives the DDS header and the chunk wrapper), written as the loose
    file photo_name(<new playerid>)."""
    _, template = game.read_photo(min(game.photo_index))
    return crest.dds_entry(template, prepare(img))


def preview(img):
    """PIL image of the photo as the game will show it (SIZE x SIZE, DXT5 compressed)."""
    buf = io.BytesIO()
    imageprep.clean(prepare(img)).save(buf, format='DDS', pixel_format='DXT5')
    return Image.open(io.BytesIO(buf.getvalue())).convert('RGBA')


def original_photo(game, playerid):
    """PIL image of an original player's photo (128 px), or None (most generic-head players have none)."""
    if playerid not in game.photo_index:
        return None
    _, raw = game.read_photo(playerid)
    return Image.open(io.BytesIO(chunk.decode(raw)))
