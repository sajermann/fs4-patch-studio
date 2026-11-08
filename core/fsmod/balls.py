"""Balls: the game's own and the ones the user adds from FIFA 16 PC packs, and the ball of each stadium.

How the game picks the ball (validated in game): the match's ball is stadiums.balltype of the stadium played (1-255;
the executable falls back to 233 without a row), used as is in the file names:
  data/sceneassets/ball/ball_<id>.rx3           mesh: one FxRenderableSimple, not skinned
  data/sceneassets/ball/ball_<id>_textures.rx3  ball_cm (color, DXT1) + ball_nm (normal map, DXT3)
and data/fifarna/lua/assets/ball.lua falls back to ball_47 when a file is missing. The game has files for 92 ids
(0-255); its stadiums use 14 of them, the rest (FIFA 12 leftovers) work as well. A new ball gets a free id (no file
in the game) as loose files under Game/data/... (inside data8 the game does not find them). An edited game ball
replaces the game's files inside data3 (for every stadium using it).

The user's ball is two files of a FIFA 16 PC pack (RX3l): ball_<id>.rx3 (the same vertex layout as the game's balls,
only little-endian: byte-swapped into the game's template ball) and ball_<id>_textures.rx3 (ball_cm DXT1, kept at
its size: 1024 works; ball_nm BC5 with x and y only: blue set to 255 and alpha to the game's average into the
template's DXT3; ball_coeff has no place in the game and is dropped).
"""
import hashlib
import struct
from collections import OrderedDict

import numpy as np
from PIL import Image

from . import boots, chunk, gloves, rx3mesh, rx3tex, scanface

BALL_DIR = 'data/sceneassets/ball/'
FILES = ('ball_{}.rx3', 'ball_{}_textures.rx3')  # mesh, textures
TEMPLATE_ID = 231  # game ball whose files a converted one is written into
IDS = range(1, 256)  # stadiums.balltype
FIELD = 'balltype'
NM_ALPHA = 146  # average alpha of the game's ball_nm
MAX_UPLOAD = 64 * 1024 * 1024
GAME_CREDITS = 'EA'
RADIUS = (5.0, 20.0)  # cm: a mesh outside this is not a ball (the game's are ~11)
VERTICES, INDICES, HEADER = 0x5878F4 + 0x1AD, 0x5878F4, 0x22B2BE36


class BallError(ValueError):
    """A file that is not a usable ball; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def original_entry(ball_id, uid):
    """Ball entry that edits the game's ball `ball_id`, as opened (no files of its own: the game's stay)."""
    from .model import Ball
    return Ball(uid=uid, name=f'Original {ball_id}', credits=GAME_CREDITS, original_id=ball_id)


def untouched(ball):
    """An edited game ball still as opened (saving drops it: the ball stays the game's)."""
    fresh = original_entry(ball.original_id, ball.uid)
    return ball.is_original and all(getattr(ball, f) == getattr(fresh, f)
                                    for f in ('name', 'credits', 'mesh', 'texture', 'thumbnail', 'hidden'))


def file_names(ball_id):
    return [BALL_DIR + f.format(ball_id) for f in FILES]


def game_ids(sources):
    """Ids the game has ball files for (cached on the sources object)."""
    ids = getattr(sources, '_ball_ids', None)
    if ids is None:
        ids = sources._ball_ids = [i for i in IDS if all(sources.locate(n) for n in file_names(i))]
    return ids


def free_ids(sources):
    taken = set(game_ids(sources))
    return [i for i in IDS if i not in taken]


def triangles(strip):
    """Triangle list of a triangle strip (degenerate triangles dropped, every other one turned back)."""
    out = []
    for k in range(len(strip) - 2):
        a, b, c = strip[k:k + 3]
        if a == b or b == c or a == c:
            continue
        out.extend((a, b, c) if k % 2 == 0 else (b, a, c))
    return out


# ---------------------------------------------------------------- reading the user's files
def _plain(data):
    if len(data) > MAX_UPLOAD:
        raise BallError('ball_file_too_big')
    return chunk.decode(data) if data[:4] == b'chun' else data


def check_mesh(data):
    """The pack's ball_<id>.rx3 (bytes, chunk-compressed or not), checked; raises BallError."""
    d = _plain(data)
    if d[:4] != b'RX3l':
        raise BallError('ball_mesh_not_pc', d[:4].hex())
    try:
        meshes = rx3mesh.meshes(d)
        dc = scanface.decl(d, '<', 0)
    except Exception as e:  # noqa: BLE001 (any parse error: not a mesh file)
        raise BallError('ball_mesh_invalid', f'{type(e).__name__}: {e}') from e
    if len(meshes) != 1 or not {'p0', 'n0', 't0'} <= set(dc) or 'w0' in dc:
        raise BallError('ball_mesh_invalid', 'not one plain mesh')
    radius = np.abs(np.array(meshes[0]['attrs']['p0'])[:, :3]).max()
    if not RADIUS[0] < radius < RADIUS[1]:
        raise BallError('ball_mesh_not_ball', f'radius {radius:.1f}')
    return d


def check_texture(data):
    """The pack's ball_<id>_textures.rx3 (bytes), checked; raises BallError."""
    d = _plain(data)
    if d[:4] != b'RX3l':
        raise BallError('ball_texture_not_pc', d[:4].hex())
    try:
        found = rx3tex.names(d)
    except Exception as e:  # noqa: BLE001
        raise BallError('ball_texture_invalid', f'{type(e).__name__}: {e}') from e
    if 'ball_cm' not in found:
        raise BallError('ball_texture_invalid', 'no ball_cm')
    return d


# ---------------------------------------------------------------- conversion
def template_files(sources):
    """The game's ball TEMPLATE_ID files (mesh, textures) as RX3b."""
    mesh, textures = game_files(sources, TEMPLATE_ID)
    return {'mesh': mesh, 'textures': textures}


def _sections_of(d, e, type_):
    return [(i, o, s) for i, (t, o, s, _) in enumerate(scanface.sections(d, e)) if t == type_]


def _mesh(template, pack):
    """Template RX3b ball with the pack's (RX3l) vertices and indices, byte-swapped attribute by attribute."""
    dc_t, dc_p = scanface.decl(template, '>', 0), scanface.decl(pack, '<', 0)
    if dc_t != dc_p:
        raise BallError('ball_mesh_layout', f'{sorted(dc_p)}')
    (_, vo, _), = _sections_of(pack, '<', VERTICES)
    _, count, stride, _ = struct.unpack('<IIII', pack[vo:vo + 16])
    vb = bytearray(pack[vo + 16:vo + 16 + count * stride])
    for i in range(count):
        b = i * stride
        for off, n, typ in dc_p.values():
            width = 2 if typ == 'f16' else 4
            for k in range(n if typ == 'f16' else 1):
                q = b + off + k * width
                vb[q:q + width] = vb[q:q + width][::-1]
    (_, io_, _), = _sections_of(pack, '<', INDICES)
    _, n_idx = struct.unpack('<II', pack[io_:io_ + 8])
    if pack[io_ + 8] != 2:
        raise BallError('ball_mesh_invalid', '32-bit indices')
    ib = struct.pack(f'>{n_idx}H', *struct.unpack_from(f'<{n_idx}H', pack, io_ + 16))
    (vi, _, _), = _sections_of(template, '>', VERTICES)
    (ii, to, _), = _sections_of(template, '>', INDICES)
    (hi, ho, hs), = _sections_of(template, '>', HEADER)
    header = bytearray(template[ho:ho + hs])
    struct.pack_into('>II', header, 16, 16 + len(ib), n_idx)
    replace = {vi: struct.pack('>IIII', 16 + len(vb), count, stride, 0) + bytes(vb),
               ii: struct.pack('>II', 16 + len(ib), n_idx) + bytes(template[to + 8:to + 16]) + ib,
               hi: bytes(header)}
    return bytes(scanface.rebuild(template, replace))


def _textures(template, pack):
    """Template textures RX3b with the pack's ball_cm (DXT1 at the pack's size) and ball_nm (the template's DXT3)."""
    d = bytearray(template)
    color = boots._decode(pack, 'ball_cm').convert('RGB')
    if color.size[0] != rx3tex.by_name(d, 'ball_cm')['w']:
        d = scanface.resize_texture(d, rx3tex.by_name(d, 'ball_cm'), *color.size)
    rx3tex.set_image_dxt1(d, rx3tex.by_name(d, 'ball_cm'), color)
    if 'ball_nm' in rx3tex.names(pack):
        a = np.asarray(boots._decode(pack, 'ball_nm').convert('RGB'), dtype=np.uint8).copy()
        a[..., 2] = 255
        nm = Image.fromarray(np.dstack([a, np.full(a.shape[:2], NM_ALPHA, np.uint8)]), 'RGBA')
        rx3tex.set_image(d, rx3tex.by_name(d, 'ball_nm'), nm)
    return bytes(d)


def _convert(tpl, mesh, texture):
    m, t = check_mesh(mesh), check_texture(texture)
    return _mesh(tpl['mesh'], m), _textures(tpl['textures'], t)


class Converter:
    """Converts the user's balls for the game, keeping the last results in memory."""

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

    def converted(self, mesh, texture):
        """(mesh, textures) RX3b of the template's id; raises BallError."""
        key = hashlib.sha1(hashlib.sha1(mesh).digest() + hashlib.sha1(texture).digest()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        out = _convert(self.template, mesh, texture)
        self._cache[key] = out
        while len(self._cache) > self.size:
            self._cache.popitem(last=False)
        return out

    def files(self, mesh, texture, ball_id):
        """{internal file name: RX3b bytes} of a ball as `ball_id` (FILES order: mesh, textures)."""
        old, new = f'ball_{TEMPLATE_ID}', f'ball_{ball_id}'
        return {name: bytes(scanface.renamed(bytearray(data), old, new))
                for name, data in zip(file_names(ball_id), self.converted(mesh, texture))}


def color_image(textures_rx3b):
    """The ball's color map (PIL RGB)."""
    return rx3tex.to_image(textures_rx3b, rx3tex.by_name(textures_rx3b, 'ball_cm')).convert('RGB')


def glb_mesh(mesh_rx3b):
    """The ball as a preview mesh (fsmod.gltf; node 'ball', triangle list)."""
    from . import preview
    m = rx3mesh.meshes(mesh_rx3b)[0]
    return preview._glb_mesh('ball', {**m, 'indices': triangles(m['indices'])})


# ---------------------------------------------------------------- thumbnails
def thumbnail(mesh_rx3b, textures_rx3b, width=256, supersample=2):
    """The ball seen from the front, textured per pixel: the list's picture when the user sends none."""
    m = rx3mesh.meshes(mesh_rx3b)[0]
    p = np.array(m['attrs']['p0'])[:, :3]
    uv = np.array(m['attrs']['t0'])[:, :2]
    nrm = np.array(m['attrs']['n0'])[:, :3]
    tris = np.array(triangles(m['indices'])).reshape(-1, 3)
    tex = np.asarray(color_image(textures_rx3b))
    size = width * supersample
    pad = size // 32
    scale = (size - 2 * pad) / (2 * np.abs(p).max())
    # front view: image x = x, image y = -y (up), depth = z (towards the viewer)
    X = size / 2 + p[:, 0] * scale
    Y = size / 2 - p[:, 1] * scale
    light = np.array([-0.4, 0.6, 0.7]) / np.linalg.norm([-0.4, 0.6, 0.7])
    shade_v = 0.45 + 0.55 * np.clip(nrm @ light, 0, 1)
    rgb, alpha = gloves.rasterize(X, Y, p[:, 2], uv, shade_v, tris, tex, size, size)
    img = Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha]), 'RGBA')
    return img.resize((width, width), Image.LANCZOS)


def game_files(sources, ball_id):
    """(mesh, textures) RX3b of one of the game's balls, for its thumbnail and preview."""
    out = []
    for name in file_names(ball_id):
        entry = sources.read_entry(name)
        if entry is None:
            raise KeyError(name)
        out.append(bytes(chunk.decode(entry[2])))
    return tuple(out)
