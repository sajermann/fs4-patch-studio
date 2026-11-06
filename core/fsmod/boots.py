"""Boots: the game's own and the ones the user adds from FIFA 14-16 PC packs.

How the game picks a boot (data/fifarna/lua/assets/player.lua): each player has one code per pitch surface and the
code goes as is into the file names (validated in game):
  street  players.shoetypecode   only codes 500-619 work there (any other: the game shows a generic sneaker)
  turf    players.turf_shoe      artificial grass (society): any code with files
  indoor  players.indoor_shoe    court (futsal): any code with files
  data/sceneassets/shoe/shoe_<code>.rx3              mesh: both feet in one submesh, skinned to the knee, ankle and toe
                                                     bones of each leg (4/5/6 and 31/32/33); feet at x = +-13.6 cm
  data/sceneassets/shoe/shoe_<code>_0_textures.rx3   shoe_cm (color)
  data/sceneassets/shoe/shoe_<code>_textures.rx3     shoe_nm (normal map, x/y/z) + shoe_coeff
The game has files for 186 codes (0-108 and 223: studded boots no player wears; 500-560 futsal/society; 600-619
street sneakers). A new boot gets a free code: 561-599 if it may go on the street (STREET_CODES has no other free
one), 620-1023 otherwise. Loose files under Game/data/... work for new codes (like the scanned faces).

The user's boot is a pair of a FIFA 14-16 PC pack (RX3l): shoe_<id>.rx3 + shoe_<id>_0_textures.rx3 (shoe_cm, shoe_nm,
shoe_coeff). Pack boots already sit where the game's do and are skinned to the same bone positions (the 400-bone
skeleton of the FIFA 14-16 faces, or the game's own numbering), so the bones map to the nearest one of the template
boot (scanface.convert_mesh). Textures are written in the game's DXT1 at TEXTURE_SIZE; the pack's normal map is BC5
(x and y only: z is rebuilt) and its coeff map means something else (the game's average is used instead).

Collar: pack boots are made for thinner socks: their collar lies on or inside the game's sock and the two cross in
game (a jagged edge). The game's own boots stay 0.4-1.5 cm outside the sock. fit_collar moves the outer shell at
least GAP outside the sock surface; laces (small separate parts) move as one piece and the shell's moves are
smoothed over its neighbors, so nothing is crushed onto the sock (validated in game).
"""
import hashlib
import io
import struct
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageDraw

from . import chunk, rx3mesh, rx3tex, scanface

SHOE_DIR = 'data/sceneassets/shoe/'
SOCK = 'data/sceneassets/body/sock_0.rx3'  # every sock's foot part is the same (the ankle sock: up to 0.32 cm wider)
TEMPLATE_CODE = 616  # game boot whose files give the layout, materials and bone palette of a converted one
SURFACE_FIELDS = {'street': 'shoetypecode', 'turf': 'turf_shoe', 'indoor': 'indoor_shoe'}  # players columns
STREET_CODES = range(500, 620)  # the only codes the street takes
NEW_CODES = range(620, 1024)  # free codes for boots that do not go on the street (field range 0-1023)
FILES = ('shoe_{}.rx3', 'shoe_{}_0_textures.rx3', 'shoe_{}_textures.rx3')
TEXTURE_SIZE = 512
BC5 = 7  # texture format of the packs' normal maps (rx3tex reads DXT1/3/5 and ARGB only)
FLAT_COEFF = (239, 44, 239)  # average shoe_coeff of the game's boots
MAX_UPLOAD = 64 * 1024 * 1024  # bytes per uploaded file

GAP = 0.5  # cm between the sock and the boot's outer shell
MARGIN = 0.3  # cm above the sock's open bottom where measuring starts (below it the foot is inside the boot)
SMALL_PART = 0.02  # separate parts with fewer positions than this share of the boot move as one piece (laces)
LACE_MAX_MOVE = 1.5  # cm (a lace end tucked deep into the boot would throw the whole lace off)
SMOOTH_PASSES = 3
ANKLE_BONE = (13.3, 11.8, -3.8)  # bind position of the right ankle (cm): a boot mesh has a bone there


class BootError(ValueError):
    """A file that is not a usable boot; `code` names the reason (texts in the API)."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


GAME_CREDITS = 'EA'


def original_entry(code, uid):
    """Boot entry that edits the game's boot `code`, as opened (no files of its own: the game's stay)."""
    from .model import Boot
    return Boot(uid=uid, name=f'Original {code}', credits=GAME_CREDITS, original_id=code)


def untouched(boot):
    """An edited game boot still as opened (saving drops it: the boot stays the game's)."""
    fresh = original_entry(boot.original_id, boot.uid)
    return boot.is_original and all(getattr(boot, f) == getattr(fresh, f)
                                    for f in ('name', 'credits', 'mesh', 'texture', 'thumbnail', 'hidden'))


def file_names(code):
    return [SHOE_DIR + f.format(code) for f in FILES]


def game_codes(sources):
    """Codes the game has files for (cached on the sources object)."""
    codes = getattr(sources, '_boot_codes', None)
    if codes is None:
        codes = sources._boot_codes = sorted(c for c in range(1024) if sources.locate(SHOE_DIR + FILES[0].format(c)))
    return codes


def free_street_codes(sources):
    taken = set(game_codes(sources))
    return [c for c in STREET_CODES if c not in taken]


def free_new_codes(sources):
    taken = set(game_codes(sources))
    return [c for c in NEW_CODES if c not in taken]


def street_ok(code):
    return code in STREET_CODES


def _plain(data):
    if len(data) > MAX_UPLOAD:
        raise BootError('boot_file_too_big')
    return chunk.decode(data) if data[:4] == b'chun' else data


# ---------------------------------------------------------------- reading the user's files
def check_mesh(data):
    """The pack's mesh RX3 (bytes, chunk-compressed or not), checked; raises BootError."""
    d = _plain(data)
    if d[:4] != b'RX3l':
        raise BootError('boot_mesh_not_pc', d[:4].hex())
    try:
        meshes = rx3mesh.meshes(d)
        dc = scanface.decl(d, '<', 0)
        bones = scanface.bone_positions(d, '<')
    except Exception as e:  # noqa: BLE001 (any parse error: not a mesh file)
        raise BootError('boot_mesh_invalid', f'{type(e).__name__}: {e}') from e
    if not meshes or not {'p0', 'n0', 't0', 'i0', 'w0'} <= set(dc):
        raise BootError('boot_mesh_invalid', 'no skinned mesh')
    if not any(np.linalg.norm(np.array(b) - (ANKLE_BONE[0] * s, *ANKLE_BONE[1:])) < 1.0
               for b in bones for s in (1, -1)):
        raise BootError('boot_mesh_not_boot', 'no ankle bone')
    return d


def check_texture(data):
    """The pack's _0_textures RX3 (bytes), checked; raises BootError."""
    d = _plain(data)
    if d[:4] != b'RX3l':
        raise BootError('boot_texture_not_pc', d[:4].hex())
    try:
        names = rx3tex.names(d)
    except Exception as e:  # noqa: BLE001
        raise BootError('boot_texture_invalid', f'{type(e).__name__}: {e}') from e
    if 'shoe_cm' not in names:
        raise BootError('boot_texture_invalid', 'no shoe_cm')
    return d


def _decode(d, name):
    t = rx3tex.by_name(d, name)
    if t['fmt'] != BC5:
        return rx3tex.to_image(d, t)
    q, n, w, h = t['levels'][0]
    hdr = (b'DDS ' + struct.pack('<7I', 124, 0x1007, h, w, n, 0, 1) + b'\0' * 44 +
           struct.pack('<2I4s5I', 32, 4, b'ATI2', 0, 0, 0, 0, 0) + struct.pack('<5I', 0x1000, 0, 0, 0, 0))
    return Image.open(io.BytesIO(hdr + d[q:q + n]))


def _full_normal(image):
    """x, y (+ empty blue) -> x, y, z = sqrt(1 - x^2 - y^2); a map that already has z is kept."""
    a = np.asarray(image.convert('RGB'), dtype=np.float32)
    if a[..., 2].mean() > 64:
        return image.convert('RGB')
    x, y = a[..., 0] / 127.5 - 1, a[..., 1] / 127.5 - 1
    a[..., 2] = (np.sqrt(np.clip(1 - x * x - y * y, 0, 1)) + 1) * 127.5
    return Image.fromarray(a.clip(0, 255).astype(np.uint8), 'RGB')


# ---------------------------------------------------------------- collar off the sock
def sock_surface(sock, ymax=24.0):
    """(triangles (T,3,3), vertex normals per corner (T,3,3)) of a sock RX3b below ymax, both feet."""
    tris, norms = [], []
    for m in rx3mesh.meshes(sock):
        p = np.array(m['attrs']['p0'])[:, :3]
        n = np.array(m['attrs']['n0'])
        idx = np.array(m['indices']).reshape(-1, 3)
        keep = p[idx][:, :, 1].min(1) < ymax
        tris.append(p[idx[keep]])
        norms.append(n[idx[keep]])
    return np.concatenate(tris), np.concatenate(norms)


def _closest_points(p, tri):
    """Closest point on every triangle of tri (T,3,3) to p, with its barycentric weights (Ericson, vectorized)."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom[denom == 0] = 1e-12
    v, w = vb / denom, vc / denom
    res = a + ab * v[:, None] + ac * w[:, None]
    bary = np.stack([1 - v - w, v, w], 1)

    def safe(x):
        return np.where(x == 0, 1e-12, x)

    for mask, point, weights in (((d1 <= 0) & (d2 <= 0), a, (1, 0, 0)),
                                 ((d3 >= 0) & (d4 <= d3), b, (0, 1, 0)),
                                 ((d6 >= 0) & (d5 <= d6), c, (0, 0, 1))):
        res[mask], bary[mask] = point[mask], weights
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t = d1 / safe(d1 - d3)
    res[m], bary[m] = (a + ab * t[:, None])[m], np.stack([1 - t, t, 0 * t], 1)[m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t = d2 / safe(d2 - d6)
    res[m], bary[m] = (a + ac * t[:, None])[m], np.stack([1 - t, 0 * t, t], 1)[m]
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = (d4 - d3) / safe((d4 - d3) + (d5 - d6))
    res[m], bary[m] = (b + (c - b) * t[:, None])[m], np.stack([0 * t, 1 - t, t], 1)[m]
    return res, bary


def signed_distance(p, tri, norms):
    """(signed distance (> 0 outside), closest point, outward normal there) of p to the sock."""
    q, bary = _closest_points(p, tri)
    k = int(np.argmin(((q - p) ** 2).sum(1)))
    n = (norms[k] * bary[k][:, None]).sum(0)
    n /= np.linalg.norm(n) + 1e-12
    return float((p - q[k]) @ n), q[k], n


def _welded(p, idx):
    """(group per vertex: vertices at the same position (UV seams) share one, neighbor groups of each group)."""
    keys = {}
    gid = np.array([keys.setdefault(tuple(np.round(v, 3)), len(keys)) for v in p])
    nb = [set() for _ in keys]
    for a, b, c in gid[idx]:
        nb[a].update((b, c))
        nb[b].update((a, c))
        nb[c].update((a, b))
    return gid, nb


def _components(nb):
    comp = -np.ones(len(nb), int)
    k = 0
    for s in range(len(nb)):
        if comp[s] >= 0:
            continue
        stack, comp[s] = [s], k
        while stack:
            u = stack.pop()
            for v in nb[u]:
                if comp[v] < 0:
                    comp[v] = k
                    stack.append(v)
        k += 1
    return comp


def fit_collar(p, normals, idx, tri, norms):
    """New positions (V,3) of a boot mesh (p, normals: (V,3); idx: (F,3)) with its outer shell off the sock.
    Inward-facing positions (lining) stay: the shell hides them (pushing them into the sock turned walls inside out)."""
    bottom = tri[:, :, 1].min() + MARGIN
    gid, nb = _welded(p, idx)
    groups = len(nb)
    gp, gn, cnt = np.zeros((groups, 3)), np.zeros((groups, 3)), np.zeros(groups)
    np.add.at(gp, gid, p)
    np.add.at(gn, gid, normals)
    np.add.at(cnt, gid, 1)
    gp /= cnt[:, None]

    def required(points):
        move = np.zeros_like(points)
        for g in np.where(points[:, 1] > bottom - 0.5)[0]:
            d, q, n = signed_distance(points[g], tri, norms)
            if q[1] < bottom or float(gn[g] @ n) < 0:
                continue
            if d < GAP:
                move[g] = q + n * GAP - points[g]
        return move

    move = required(gp)
    comp = _components(nb)
    sizes = np.bincount(comp)
    for k in np.where(sizes < SMALL_PART * groups)[0]:
        members = comp == k
        need = np.linalg.norm(move[members], axis=1) > 0
        if not need.any():
            continue
        direction = move[members][need].mean(0)
        direction /= np.linalg.norm(direction) + 1e-12
        length = float(np.percentile(move[members][need] @ direction, 80))
        move[members] = direction * min(max(length, 0.0), LACE_MAX_MOVE)
    main = sizes[comp] >= SMALL_PART * groups
    for _ in range(SMOOTH_PASSES):
        smoothed = move.copy()
        for g in np.where(main)[0]:
            if nb[g]:
                avg = np.mean([move[h] for h in nb[g]], 0)
                smoothed[g] = avg if np.linalg.norm(avg) > np.linalg.norm(move[g]) else (move[g] + avg) / 2
        move = smoothed
    out = gp + move
    out[main] += required(out)[main]
    return out[gid]


def _with_positions(d, positions):
    """RX3b d (one mesh, p0 = 3 x f32 at offset 0) with new vertex positions."""
    d = bytearray(d)
    o, _ = scanface.of_type(d, '>', scanface.VERTICES)[0]
    _, count, stride, _ = struct.unpack('>IIII', d[o:o + 16])
    if scanface.decl(d, '>', 0)['p0'] != (0, 3, 'f32') or count != len(positions):
        raise BootError('boot_mesh_invalid', 'unexpected vertex layout')
    for i, v in enumerate(positions):
        struct.pack_into('>3f', d, o + 16 + i * stride, *map(float, v))
    return bytes(d)


# ---------------------------------------------------------------- conversion
def template_files(sources):
    """What every conversion needs from the original files: the template boot's three RX3b files and the sock."""
    def read(name):
        entry = sources.read_entry(name)
        if entry is None:
            raise KeyError(name)
        return bytearray(chunk.decode(entry[2]))
    mesh, color, maps = (read(n) for n in file_names(TEMPLATE_CODE))
    return {'mesh': mesh, 'color': color, 'maps': maps, 'sock': sock_surface(read(SOCK))}


def _with_textures(template, images):
    d = bytearray(template)
    for name, image in images.items():
        d = scanface.resize_texture(d, rx3tex.by_name(d, name), TEXTURE_SIZE, TEXTURE_SIZE)
        rx3tex.set_image_dxt1(d, rx3tex.by_name(d, name), image.convert('RGB'))
    return d


def _convert(tpl, mesh, texture):
    """(mesh RX3b, color RX3b, maps RX3b) named with the template's code."""
    m = check_mesh(mesh)
    t = check_texture(texture)
    old = f'shoe_{TEMPLATE_CODE}'
    converted = bytes(scanface.convert_mesh(tpl['mesh'], m, [0], old, old))
    mm = rx3mesh.meshes(converted)[0]
    fitted = fit_collar(np.array(mm['attrs']['p0'])[:, :3], np.array(mm['attrs']['n0']),
                        np.array(mm['indices']).reshape(-1, 3), *tpl['sock'])
    names = rx3tex.names(t)
    normal = _full_normal(_decode(t, 'shoe_nm')) if 'shoe_nm' in names else Image.new('RGB', (4, 4), (128, 128, 255))
    color = _with_textures(tpl['color'], {'shoe_cm': _decode(t, 'shoe_cm')})
    maps = _with_textures(tpl['maps'], {'shoe_nm': normal, 'shoe_coeff': Image.new('RGB', (4, 4), FLAT_COEFF)})
    return _with_positions(converted, fitted), bytes(color), bytes(maps)


class Converter:
    """Converts the user's boots for the game, keeping the last results in memory (conversion takes ~1-2 s)."""

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
        """(mesh, color, maps) RX3b of the template's code; raises BootError."""
        key = hashlib.sha1(hashlib.sha1(mesh).digest() + hashlib.sha1(texture).digest()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        out = _convert(self.template, mesh, texture)
        self._cache[key] = out
        while len(self._cache) > self.size:
            self._cache.popitem(last=False)
        return out

    def files(self, mesh, texture, code):
        """{internal file name: RX3b bytes} of a boot as `code` (FILES order: mesh, color, maps)."""
        old, new = f'shoe_{TEMPLATE_CODE}', f'shoe_{code}'
        return {name: bytes(scanface.renamed(bytearray(data), old, new))
                for name, data in zip(file_names(code), self.converted(mesh, texture))}


# ---------------------------------------------------------------- thumbnails
def thumbnail(mesh_rx3b, color_rx3b, width=256):
    """Side view of the right boot (outer side), colored from its texture: the list's picture when the user sends
    none. Flat-shaded triangles drawn back to front."""
    m = rx3mesh.meshes(mesh_rx3b)[0]
    p = np.array(m['attrs']['p0'])[:, :3]
    uv = np.array(m['attrs']['t0'])
    nrm = np.array(m['attrs']['n0'])
    idx = np.array(m['indices']).reshape(-1, 3)
    tex = np.asarray(rx3tex.to_image(color_rx3b, rx3tex.textures(color_rx3b)[0]).convert('RGB'))
    th, tw = tex.shape[:2]
    tris = idx[(p[idx][:, :, 0] > 0).all(1)]
    right = p[p[:, 0] > 0]
    lo, hi = right.min(0), right.max(0)
    pad = width // 16
    scale = (width - 2 * pad) / max(hi[2] - lo[2], hi[1] - lo[1])
    height = int((hi[1] - lo[1]) * scale) + 2 * pad
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    light = np.array([0.6, 0.6, 0.5]) / np.linalg.norm([0.6, 0.6, 0.5])
    for t in tris[np.argsort(p[tris][:, :, 0].mean(1))]:
        n = nrm[t].mean(0)
        n /= np.linalg.norm(n) + 1e-12
        if n[0] < -0.05:
            continue
        u, v = uv[t].mean(0)
        c = tex[min(th - 1, max(0, int(v * th))), min(tw - 1, max(0, int(u * tw)))]
        shade = 0.55 + 0.45 * max(0.0, float(n @ light))
        draw.polygon([(pad + (p[j][2] - lo[2]) * scale, height - pad - (p[j][1] - lo[1]) * scale) for j in t],
                     fill=tuple(int(x * shade) for x in c) + (255,))
    return img


def game_files(sources, code):
    """(mesh, color) RX3b of one of the game's own boots, for its thumbnail and preview."""
    out = []
    for name in file_names(code)[:2]:
        entry = sources.read_entry(name)
        if entry is None:
            raise KeyError(name)
        out.append(bytes(chunk.decode(entry[2])))
    return tuple(out)
