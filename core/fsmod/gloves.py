"""Goalkeeper gloves: the game's own and the ones the user adds from FIFA 16 PC packs.

How the game builds a glove (data/fifarna/lua/assets/accessory.lua, accessory model 18, validated in game): the
goalkeeper gets an accessory whose color is players.gkglovetypecode (0-63), used as is in the file names:
  data/sceneassets/gkglove/gkglove_0_0.rx3              mesh: both hands, the same for every glove (never changed)
  data/sceneassets/gkglove/gkglove_0_<code>_cm.rx3      gkglove_cm (color, DXT1 512x256)
  data/sceneassets/gkglove/gkglove_0_<code>_textures.rx3  gkglove_nm (normal map) + gkglove_coeff (DXT1 256x256)
Only players whose preferredposition1 is the goalkeeper's (0) wear their own glove; anyone else put in goal wears the
game's default one (see preferred_position). The game has files for 18 codes (1-5, 30-32, 40-49); code 0 has none.
A new glove gets one of the free codes (FREE_CODES: 45) as loose files under Game/data/... (inside data8 the game finds
them but shows a broken texture). An edited game glove replaces the game's files inside data3.

The user's glove is one file of a FIFA 16 PC pack (RX3l): gkglove_<id>_textures.rx3 with gkglove_cm (same layout and
size as the game's: the FIFA 16 glove UV map is the game's), gkglove_nm (BC5: x and y only, z is rebuilt) and
gkglove_coeff (the same generic map in every glove: the game's own glove 1 coeff is kept). The game's template files
are rewritten with the pack's images, so a converted glove has exactly the size of an original one.
"""
import hashlib
from collections import Counter, OrderedDict

import numpy as np
from PIL import Image

from . import boots, chunk, rx3mesh, rx3tex

GLOVE_DIR = 'data/sceneassets/gkglove/'
MESH = GLOVE_DIR + 'gkglove_0_0.rx3'
FILES = ('gkglove_0_{}_cm.rx3', 'gkglove_0_{}_textures.rx3')  # color, maps
TEMPLATE_CODE = 1  # game glove whose files a converted one is written into
CODES = range(1, 64)  # players.gkglovetypecode is 0-63; 0 = no glove of its own
FIELD = 'gkglovetypecode'
GOALKEEPER = 0  # preferredposition1 / teamplayerlinks.position of the goalkeeper
NOT_A_POSITION = (28, 29)  # teamplayerlinks SUB / RES: no preferred position
FALLBACK_POSITION = 25  # ST: a player without glove nor position in any team
MAX_UPLOAD = 64 * 1024 * 1024
GAME_CREDITS = 'EA'


class GloveError(ValueError):
    """A file that is not a usable glove; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def original_entry(code, uid):
    """Glove entry that edits the game's glove `code`, as opened (no file of its own: the game's stay)."""
    from .model import Glove
    return Glove(uid=uid, name=f'Original {code}', credits=GAME_CREDITS, original_id=code)


def untouched(glove):
    """An edited game glove still as opened (saving drops it: the glove stays the game's)."""
    fresh = original_entry(glove.original_id, glove.uid)
    return glove.is_original and all(getattr(glove, f) == getattr(fresh, f)
                                     for f in ('name', 'credits', 'texture', 'thumbnail', 'hidden'))


def file_names(code):
    return [GLOVE_DIR + f.format(code) for f in FILES]


def game_codes(sources):
    """Codes the game has glove files for (cached on the sources object)."""
    codes = getattr(sources, '_glove_codes', None)
    if codes is None:
        codes = sources._glove_codes = [c for c in CODES if sources.locate(GLOVE_DIR + FILES[0].format(c))]
    return codes


def free_codes(sources):
    taken = set(game_codes(sources))
    return [c for c in CODES if c not in taken]


# ---------------------------------------------------------------- preferred position
def preferred_position(player, current=None):
    """players.preferredposition1 the app writes for a project player: the goalkeeper's when the user picked him a
    glove (only goalkeepers wear their own glove in the game), otherwise the position he has in most of his teams
    (a tie goes to the one of his first team; SUB/RES and unknown positions do not count), FALLBACK_POSITION when he
    has none. current = an original player's own preferred position: it stays unless the rule turns him into a
    goalkeeper or out of one (the game's finer choice, e.g. LB for a player listed as LWB, is kept)."""
    computed = _computed_position(player)
    if current is not None and (computed == GOALKEEPER) == (current == GOALKEEPER):
        return current
    return computed


def _computed_position(player):
    if player.glove is not None:
        return GOALKEEPER
    positions = [lk.position for lk in player.teams if lk.position is not None and lk.position not in NOT_A_POSITION]
    if not positions:
        return FALLBACK_POSITION
    count = Counter(positions)
    best = max(count.values())
    return next(p for p in positions if count[p] == best)


# ---------------------------------------------------------------- reading the user's file
def check_texture(data):
    """The pack's gkglove_<id>_textures.rx3 (bytes, chunk-compressed or not), checked; raises GloveError."""
    if len(data) > MAX_UPLOAD:
        raise GloveError('glove_file_too_big')
    d = chunk.decode(data) if data[:4] == b'chun' else data
    if d[:4] != b'RX3l':
        raise GloveError('glove_texture_not_pc', d[:4].hex())
    try:
        found = rx3tex.names(d)
    except Exception as e:  # noqa: BLE001 (any parse error: not a texture file)
        raise GloveError('glove_texture_invalid', f'{type(e).__name__}: {e}') from e
    if 'gkglove_cm' not in found:
        raise GloveError('glove_texture_invalid', 'no gkglove_cm')
    return d


# ---------------------------------------------------------------- conversion
def template_files(sources):
    """The game's glove TEMPLATE_CODE files (color, maps) as RX3b, and the glove mesh."""
    def read(name):
        entry = sources.read_entry(name)
        if entry is None:
            raise KeyError(name)
        return bytes(chunk.decode(entry[2]))
    color, maps = (read(n) for n in file_names(TEMPLATE_CODE))
    return {'color': color, 'maps': maps, 'mesh': read(MESH)}


def _color(template, pack):
    """Template color RX3b with the pack's gkglove_cm: its DXT1 blocks copied as they are when the layout matches
    (byte pairs swapped for the Xbox file), else decoded and encoded again."""
    d = bytearray(template)
    dst, src = rx3tex.by_name(d, 'gkglove_cm'), rx3tex.by_name(pack, 'gkglove_cm')
    same = (src['fmt'], src['w'], src['h']) == (dst['fmt'], dst['w'], dst['h']) and \
        [n for _, n, _, _ in src['levels']] == [n for _, n, _, _ in dst['levels']]
    if same:
        for (q, n, _, _), (p, _, _, _) in zip(dst['levels'], src['levels']):
            d[q:q + n] = rx3tex.swap16(pack[p:p + n])
    else:
        rx3tex.set_image_dxt1(d, dst, boots._decode(pack, 'gkglove_cm').convert('RGB'))
    return bytes(d)


def _maps(template, pack):
    """Template maps RX3b with the pack's normal map (the template's own size); the coeff map stays the game's."""
    d = bytearray(template)
    if 'gkglove_nm' in rx3tex.names(pack):
        normal = boots._full_normal(boots._decode(pack, 'gkglove_nm'))
        rx3tex.set_image_dxt1(d, rx3tex.by_name(d, 'gkglove_nm'), normal)
    return bytes(d)


def _convert(tpl, texture):
    t = check_texture(texture)
    return _color(tpl['color'], t), _maps(tpl['maps'], t)


class Converter:
    """Converts the user's gloves for the game, keeping the last results in memory."""

    def __init__(self, sources, size=64):
        self.sources = sources
        self._tpl = None
        self._cache = OrderedDict()
        self.size = size

    @property
    def template(self):
        if self._tpl is None:
            self._tpl = template_files(self.sources)
        return self._tpl

    def converted(self, texture):
        """(color, maps) RX3b; raises GloveError."""
        key = hashlib.sha1(texture).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        out = _convert(self.template, texture)
        self._cache[key] = out
        while len(self._cache) > self.size:
            self._cache.popitem(last=False)
        return out

    def files(self, texture, code):
        """{internal file name: RX3b bytes} of a glove as `code` (color, maps). The files carry no code inside."""
        return dict(zip(file_names(code), self.converted(texture)))


# ---------------------------------------------------------------- thumbnails
def thumbnail(mesh_rx3b, color_rx3b, width=256, supersample=2):
    """Back of the right hand seen from above, textured per pixel: the list's picture when the user sends none.
    A small z-buffered rasterizer (numpy), drawn at `supersample` times the size and scaled down."""
    m = rx3mesh.meshes(mesh_rx3b)[0]
    p = np.array(m['attrs']['p0'])[:, :3]
    uv = np.array(m['attrs']['t0'])[:, :2]
    nrm = np.array(m['attrs']['n0'])[:, :3]
    idx = np.array(m['indices']).reshape(-1, 3)
    tex = np.asarray(rx3tex.to_image(color_rx3b, rx3tex.textures(color_rx3b)[0]).convert('RGB'))
    th, tw = tex.shape[:2]
    tris = idx[(p[idx][:, :, 0] > 0).all(1)]  # right hand
    # seen from above: image x = x, image y = z (towards the viewer at the bottom), depth = y
    sx, sy, depth = p[:, 0], p[:, 2], p[:, 1]
    used = np.unique(tris)
    lo = np.array([sx[used].min(), sy[used].min()])
    hi = np.array([sx[used].max(), sy[used].max()])
    size = width * supersample
    pad = size // 16
    scale = (size - 2 * pad) / max(hi - lo)
    h = int((hi[1] - lo[1]) * scale) + 2 * pad
    X = (size - (hi[0] - lo[0]) * scale) / 2 + (sx - lo[0]) * scale  # centered
    Y = pad + (sy - lo[1]) * scale
    light = np.array([0.3, 0.9, 0.4]) / np.linalg.norm([0.3, 0.9, 0.4])
    shade_v = 0.5 + 0.5 * np.clip(nrm @ light, 0, 1)
    rgb = np.zeros((h, size, 3), np.float32)
    alpha = np.zeros((h, size), np.uint8)
    zb = np.full((h, size), -np.inf)
    for t in tris:
        x, y, z = X[t], Y[t], depth[t]
        x0, x1 = max(0, int(np.floor(x.min()))), min(size - 1, int(np.ceil(x.max())))
        y0, y1 = max(0, int(np.floor(y.min()))), min(h - 1, int(np.ceil(y.max())))
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if x1 < x0 or y1 < y0 or abs(den) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        w0, w1, w2 = w0[inside], w1[inside], w2[inside]
        px, py = (gx[inside] - 0.5).astype(int), (gy[inside] - 0.5).astype(int)
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        front = zz > zb[py, px]
        if not front.any():
            continue
        px, py, w0, w1, w2, zz = px[front], py[front], w0[front], w1[front], w2[front], zz[front]
        u = w0 * uv[t[0], 0] + w1 * uv[t[1], 0] + w2 * uv[t[2], 0]
        v = w0 * uv[t[0], 1] + w1 * uv[t[1], 1] + w2 * uv[t[2], 1]
        shade = w0 * shade_v[t[0]] + w1 * shade_v[t[1]] + w2 * shade_v[t[2]]
        texel = tex[np.clip((v * th).astype(int), 0, th - 1), np.clip((u * tw).astype(int), 0, tw - 1)]
        zb[py, px] = zz
        rgb[py, px] = texel * shade[:, None]
        alpha[py, px] = 255
    img = Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha]), 'RGBA')
    return img.resize((width, max(1, h // supersample)), Image.LANCZOS)


def game_files(sources, code):
    """(mesh, color) RX3b of one of the game's gloves, for its thumbnail."""
    out = [template_files(sources)['mesh']]
    entry = sources.read_entry(file_names(code)[0])
    if entry is None:
        raise KeyError(code)
    out.append(bytes(chunk.decode(entry[2])))
    return tuple(out)
