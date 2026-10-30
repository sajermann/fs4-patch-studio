"""Scanned faces from FIFA 14 PC packs (RX3l, little-endian) converted into FIFA Street files (RX3b, big-endian).

Converter with the options validated in game (align, fit neck, face vote, paint scalp, template eyes,
rich hair LOD). A scanned head of the game is the template (Messi,
158023): it keeps its skeleton (bone matrices), bone palette and materials; only the vertex/index buffers, the
names and the texture pixels are replaced.

Files (same names in the pack's screenassets/ and the game's data/sceneassets/, <id> = playerassetid; the game
loads them for headclasscode 0, see player.lua):
  heads/head_<id>_0.rx3                         meshes head + eyes                          data3
  faces/face_<id>_0_0_0_0_0_0_0_0_textures.rx3  face texture (FIFA 14 adds a white head_sk)  data3
  heads/eyes_<id>_0_textures.rx3                eyes (the template's eyeball is used)        data3
  hair/hair_<id>_0_0.rx3, hair_<id>_0_textures   near hair: cap alphaA + strands alphaB      data3
  hairlod/hairlod_<id>_0_0.rx3                  far hair (normal play camera): cap only      data7

Vertex conversion: FIFA 14 heads use up to 8 bone influences with u16 indices into a 400-bone skeleton; FIFA
Street uses 4 influences with u8 indices into its own 252-bone skeleton, in the same space (cm, head between
y=148 and 184). Each FIFA 14 bone is mapped to a bone the template mesh already uses (its bone palette stays
valid): by vote for the face (vote_map), by distance elsewhere.
"""
import math
import os
import shutil
import struct

from PIL import Image, ImageChops, ImageFilter

from . import chunk, rx3mesh, rx3tex

HEADER, DECL, NAMES, INDICES, VERTICES, BONES = 0x22B2BE36, 0xC28193F0, 0x4C9B9EB2, 0x005878F4, 0x00587AA1, 0xDF9AEC1E
TEXTURE, TEXTURE_HEADERS = 0x7A0B60DA, 0x6BD085DC
ASSETS = 'data/sceneassets/'
TEMPLATE = 158023  # Messi: skeleton, bone palette and materials of every converted face
# Hair cap pulled towards the scalp (cap_to_scalp; validated in game):
# packs model the cap ~0.6 cm (up to 2 cm) above the skin; FIFA 14-16's hair shader hides the gap, FIFA Street shows it
# (short/bald hair looked "lifted" near the ears and the nape). Always on. To go back: CAP_GAP = None.
CAP_GAP = 0.2  # cm: highest distance of a cap vertex above the scalp
CAP_SMOOTH = 3  # passes of neighbor averaging of the pull (keeps the cap smooth)
# Hair converters (ScannedFace.hair_mode), picked per face in the editor while watching the preview: packs build hair
# in different ways, e.g. a cap + strands pair, or the whole hair as one "cap" mesh of curl cards textured with a
# 2048-wide curl atlas, and no single conversion suits all of them. Each mode is a list of steps (see convert);
# 'standard' is the conversion validated in game and stays the default.
HAIR_MODES = {
    'standard': ('pull',),
    'volume': (),  # the pack's hair shape as it is (no pull: curls and quiffs keep their height)
    'split': ('split', 'dense', 'pull'),
    'split_sharp': ('split', 'dense', 'sharp', 'pull'),  # bigger textures: loaded fine in game (Hugo Souza, 28/10)
    'split_sharp_thick': ('split', 'dense', 'sharp', 'thick', 'pull'),
}
SPLIT_REACH = 1.0  # cm: cap triangles with a vertex farther than this above the scalp become strands ('split')
SHARP_MAX = 2048  # px: largest side of the hair textures kept by 'sharp' (the template's are 256 and 512)
THICK_GAMMA = 0.6  # exponent of the opacities in 'thick' (< 1: soft strand edges get more opaque)
# 'thick' as the editor shows it (ScannedFace.hair_thickness): exponent = 1 - thickness, so 0 = as in the pack
HAIR_THICKNESS = round(1 - THICK_GAMMA, 2)
HAIR_THICKNESS_MAX = 0.9
# kind -> file name (format with the id), relative to screenassets/ (pack) or data/sceneassets/ (game)
FILES = {'head': 'heads/head_{}_0.rx3', 'face': 'faces/face_{}_0_0_0_0_0_0_0_0_textures.rx3',
         'eyes': 'heads/eyes_{}_0_textures.rx3', 'hair': 'hair/hair_{}_0_0.rx3',
         'hair_textures': 'hair/hair_{}_0_textures.rx3', 'hairlod': 'hairlod/hairlod_{}_0_0.rx3'}
REQUIRED = ('head', 'face')
PROJECT_DIR = 'faces'  # project folder: faces/<player uid>/<FILES names with the pack id>


def project_face_dir(project_folder, player_uid):
    return os.path.join(project_folder, PROJECT_DIR, player_uid)


def read_files(folder, face_id):
    """{kind: bytes} of the FILES of a face found under folder (a pack's screenassets or a project face dir).
    Some packs ship EA-compressed files (chunkzip, e.g. 276589 in Faces-Copa-Libertadores): returned decoded."""
    out = {}
    for kind, f in FILES.items():
        path = os.path.join(folder, *f.format(face_id).split('/'))
        if os.path.isfile(path):
            with open(path, 'rb') as fh:
                data = fh.read()
            out[kind] = chunk.decode(data) if data[:4] == b'chun' else data
    return out


def write_files(folder, face_id, files):
    """Stores {kind: bytes} under folder with the FILES names (replacing what was there)."""
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    for kind, data in files.items():
        path = os.path.join(folder, *FILES[kind].format(face_id).split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data)


def sections(d, e):
    n = struct.unpack(e + 'I', d[12:16])[0]
    return [struct.unpack(e + 'IIII', d[16 + 16 * i:32 + 16 * i]) for i in range(n)]


def of_type(d, e, type_):
    return [(o, s) for t, o, s, _ in sections(d, e) if t == type_]


def decl(d, e, k):
    o, s = of_type(d, e, DECL)[k]
    out = {}
    for tok in d[o + 16:o + s].split(b'\0')[0].decode().split():
        name, off, _, _, fmt = tok.split(':')
        out[name] = (int(off, 16), int(fmt[0]), fmt[1:])
    return out


def bone_positions(d, e):
    """Bind position of every bone (inverse of the rigid inverse-bind matrices)."""
    o, s = of_type(d, e, BONES)[0]
    out = []
    for i in range((s - 16) // 64):
        m = struct.unpack_from(e + '16f', d, o + 16 + 64 * i)
        rot, t = (m[0:3], m[4:7], m[8:11]), m[12:15]
        out.append(tuple(-sum(t[k] * rot[j][k] for k in range(3)) for j in range(3)))
    return out


def used_bones(d, e, k, dc):
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    ioff, n, typ = dc['i0']
    woff = dc['w0'][0]
    used = set()
    for i in range(count):
        b = o + 16 + i * stride
        idx = struct.unpack_from(e + ('4B' if typ == 'u8' else '4H'), d, b + ioff)
        used.update(x for x, w in zip(idx, d[b + woff:b + woff + 4]) if w)
    return used


def nearest_map(src_pos, dst_pos, allowed):
    def dist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))
    return {i: min(allowed, key=lambda j: dist(p, dst_pos[j])) for i, p in enumerate(src_pos)}


def positions(d, e, k):
    """[(x, y, z)] of mesh k (heads: 3 x f32; hair: 4 x f16)."""
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    off, n, typ = decl(d, e, k)['p0']
    fmt = e + ('3f' if typ == 'f32' else '3e')
    return [struct.unpack_from(fmt, d, o + 16 + i * stride + off) for i in range(count)]


def _closest_on_triangle(p, a, b, c):
    """Closest point to p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    def sub(u, v): return (u[0] - v[0], u[1] - v[1], u[2] - v[2])
    def dot(u, v): return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    def lin(u, v, s): return (u[0] + v[0] * s, u[1] + v[1] * s, u[2] + v[2] * s)
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = sub(p, b)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return lin(a, ab, d1 / (d1 - d3))
    cp = sub(p, c)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return lin(a, ac, d2 / (d2 - d6))
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        return lin(b, sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6)))
    den = 1 / (va + vb + vc)
    return lin(lin(a, ab, vb * den), ac, vc * den)


def neck_fitter(template, slot, top=160.5, full=158.0):
    """Function that lays the FIFA 14 neck base onto the template's neck surface (closest point on its triangles):
    FIFA 14 necks are wider, stick out in front and have side/back flaps where the template has no mesh, so they
    go through the collars of FIFA Street's shirts. Whole below `full`, fading out up to `top` (below the chin)."""
    pos = positions(template, '>', slot)
    o, _ = of_type(template, '>', INDICES)[slot]
    n = struct.unpack('>I', template[o + 4:o + 8])[0]
    idx = struct.unpack_from(f'>{n}H', template, o + 16)
    tris = [tuple(pos[i] for i in idx[t:t + 3]) for t in range(0, n - 2, 3)
            if min(pos[i][1] for i in idx[t:t + 3]) < top + 2]

    def fit(p):
        if p[1] >= top:
            return p
        best = min((_closest_on_triangle(p, *tri) for tri in tris),
                   key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2)
        t = min(1.0, (top - p[1]) / (top - full))
        return tuple(a + (b - a) * t for a, b in zip(p, best))
    return fit


def s10n(v):
    out = []
    for k in range(3):
        x = (v >> (10 * k)) & 0x3FF
        out.append((x - 0x400 if x & 0x200 else x) / 511.0)
    return out


def neck_weights(template, slot, dd, below=160.0):
    """Function (pos, normal) -> (indices, weights) of the nearest template vertex facing the same way, below the
    chin (None above it: the face keeps its voted bone map). The template's neck base hangs on the torso bone and
    follows the shirt; mapped by position, the FIFA 14 neck base landed on neck bones that follow the head and
    tore out of the collars."""
    o, _ = of_type(template, '>', VERTICES)[slot]
    _, count, stride, _ = struct.unpack('>IIII', template[o:o + 16])
    ioff, woff, noff = dd['i0'][0], dd['w0'][0], dd['n0'][0]
    pts = []
    for i in range(count):
        b = o + 16 + i * stride
        p = struct.unpack_from('>3f', template, b)
        if p[1] < below + 3:
            n = s10n(struct.unpack_from('>I', template, b + noff)[0])
            pts.append((p, n, template[b + ioff:b + ioff + 4], template[b + woff:b + woff + 4]))

    def lookup(p, n):
        if p[1] >= below:
            return None

        def cost(q):
            d = sum((a - c) ** 2 for a, c in zip(p, q[0]))
            facing = sum(a * c for a, c in zip(n, q[1]))
            return d + (100.0 if facing < 0.3 else 0.0)  # same side of the surface
        q = min(pts, key=cost)
        return q[2], q[3]
    return lookup


def vertex_bones(d, e, k, dd):
    """[(position, {bone: weight})] of mesh k (both influence sets)."""
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    out = []
    for i in range(count):
        b = o + 16 + i * stride
        bw = {}
        for iname, wname in (('i0', 'w0'), ('i1', 'w1')):
            if iname in dd:
                fmt = e + ('4B' if dd[iname][2] == 'u8' else '4H')
                for x, w in zip(struct.unpack_from(fmt, d, b + dd[iname][0]), d[b + dd[wname][0]:b + dd[wname][0] + 4]):
                    if w:
                        bw[x] = bw.get(x, 0) + w
        out.append((struct.unpack_from(e + '3f', d, b), bw))
    return out


def mouth_slit(d, e, k):
    """Height (y, cm) of the mouth slit: midway between the upper teeth (hanging only on the head bone, the one
    the eyes use) and the lower teeth (not on it). Teeth = vertices inside the head (z > 3) above y=160 mapped to
    the bottom strip of the face texture (v >= 0.86), where both games draw the teeth."""
    dd = decl(d, e, k)
    head = min(used_bones(d, e, 1, decl(d, e, 1)))
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    upper, lower = [], []
    for i, (p, bw) in enumerate(vertex_bones(d, e, k, dd)):
        v = struct.unpack_from(e + '2e', d, o + 16 + i * stride + dd['t0'][0])[1]
        if v < 0.86 or p[1] < 160 or p[2] < 3:
            continue
        share = bw.get(head, 0) / sum(bw.values())
        if share > 0.9:
            upper.append(p[1])
        elif share < 0.1:
            lower.append(p[1])
    return (sum(upper) / len(upper) + sum(lower) / len(lower)) / 2


def jaw_family(verts, head_bone, threshold=0.25):
    """Bones that move with the jaw: the jaw is the most weighted bone of the face (y >= 160) after the head bone;
    a bone belongs to its family when at least `threshold` of its vertices also hang on the jaw (lower lip and chin
    bones are the jaw's children, so they share its vertices: FS 169/171/173 30-40%, chin 179 99%, upper lip
    195/197/199 0-10%; FIFA 14 lower lip 46/96/97 29-38%, chin 29 100%, upper lip 72/73/98 0%)."""
    total = {}
    for p, bw in verts:
        if p[1] >= 160:
            for x, w in bw.items():
                total[x] = total.get(x, 0) + w
    jaw = max((x for x in total if x != head_bone), key=total.get)
    count, shared = {}, {}
    for _, bw in verts:
        for x in bw:
            count[x] = count.get(x, 0) + 1
            shared[x] = shared.get(x, 0) + (jaw in bw)
    return jaw, {x for x in count if shared[x] >= threshold * count[x]}


def mirrors(bones, tol=0.8):
    """{bone: its left/right twin} by bind position (x mirrored); central bones (|x| < 0.3) map to themselves."""
    out = {}
    for i, (x, y, z) in enumerate(bones):
        if abs(x) < 0.3:
            out[i] = i
            continue
        j = min(range(len(bones)), key=lambda j: (bones[j][0] + x) ** 2 + (bones[j][1] - y) ** 2 + (bones[j][2] - z) ** 2)
        if (bones[j][0] + x) ** 2 + (bones[j][1] - y) ** 2 + (bones[j][2] - z) ** 2 < tol * tol:
            out[i] = j
    return out


def vote_map(src, k, template, slot, offset, fallback):
    """Bone map FIFA 14 -> FIFA Street by vote: every source vertex (moved by offset) looks up the nearest template
    vertex facing the same way, and each pair of bones (source bone x template bone) gets the product of their
    weights; each source bone goes to the template bone with most votes (fallback for bones without votes).

    Keeps FIFA 14's own skinning, so its split between upper lip and lower lip/jaw survives (copying the weights
    vertex by vertex mixed them up where the two mouths do not line up: open mouths became a stretched curtain).
    A bone of the jaw family (jaw_family) only takes votes for template bones of that family, so a lower lip bone
    can never land on an upper lip bone even where the two mouths sit at slightly different heights. The other
    bones vote freely: the family test misses jaw children that rarely share vertices with the jaw (FIFA 14 lower
    teeth, bone 27: 17%), and they must still reach the jaw (Messi's lower teeth hang on it directly)."""
    sd, td = decl(src, '<', k), decl(template, '>', slot)
    src_head = min(used_bones(src, '<', 1, decl(src, '<', 1)))
    tpl_head = min(used_bones(template, '>', 1, decl(template, '>', 1)))
    src_jaw, src_family = jaw_family(vertex_bones(src, '<', k, sd), src_head)
    tpl_jaw, tpl_family = jaw_family(vertex_bones(template, '>', slot, td), tpl_head)
    o, _ = of_type(template, '>', VERTICES)[slot]
    _, count, stride, _ = struct.unpack('>IIII', template[o:o + 16])
    cells, reach = {}, 2.0
    for i in range(count):
        b = o + 16 + i * stride
        p = struct.unpack_from('>3f', template, b)
        n = s10n(struct.unpack_from('>I', template, b + td['n0'][0])[0])
        bones = [(x, w) for x, w in zip(template[b + td['i0'][0]:b + td['i0'][0] + 4],
                                        template[b + td['w0'][0]:b + td['w0'][0] + 4]) if w]
        cells.setdefault(tuple(int(c // reach) for c in p), []).append((p, n, bones))
    o, _ = of_type(src, '<', VERTICES)[k]
    _, count, stride, _ = struct.unpack('<IIII', src[o:o + 16])
    votes = {}
    for i in range(count):
        b = o + 16 + i * stride
        p = [c + d for c, d in zip(struct.unpack_from('<3f', src, b), offset)]
        n = s10n(struct.unpack_from('<I', src, b + sd['n0'][0])[0])
        best, hit = None, None
        for r in (1, 2, 3):
            c0 = [int(c // reach) for c in p]
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        for q in cells.get((c0[0] + dx, c0[1] + dy, c0[2] + dz), ()):
                            if sum(a * c for a, c in zip(n, q[1])) < 0.3:
                                continue
                            d = sum((a - c) ** 2 for a, c in zip(p, q[0]))
                            if best is None or d < best:
                                best, hit = d, q
            if hit:
                break
        if not hit:
            continue
        for iname, wname in (('i0', 'w0'), ('i1', 'w1')):
            if iname not in sd:
                continue
            for x, w in zip(struct.unpack_from(_index_format(sd[iname]), src, b + sd[iname][0]),
                            src[b + sd[wname][0]:b + sd[wname][0] + 4]):
                if w:
                    for tb, tw in hit[2]:
                        if x in src_family and tb not in tpl_family:
                            continue
                        votes.setdefault(x, {}).setdefault(tb, 0)
                        votes[x][tb] += w * tw
    # faces are symmetric: a bone and its twin share their votes (seen mirrored), so both sides land alike
    src_twin, tpl_twin = mirrors(bone_positions(src, '<')), mirrors(bone_positions(template, '>'))
    merged = {}
    for b, tally in votes.items():
        m = dict(tally)
        t = src_twin.get(b)
        if t is not None and t != b:
            for tb, w in votes.get(t, {}).items():
                if tb in tpl_twin:
                    m[tpl_twin[tb]] = m.get(tpl_twin[tb], 0) + w
        merged[b] = m
    votes = merged
    out = {}
    for b in fallback:
        if b in votes:
            out[b] = max(votes[b], key=votes[b].get)
        elif b in src_family:
            out[b] = tpl_jaw
        else:
            out[b] = fallback[b] if fallback[b] not in tpl_family else tpl_head
    out[src_head], out[src_jaw] = tpl_head, tpl_jaw
    return out


def _index_format(attr):
    """struct format of a FIFA 14 bone index attribute: most packs use 2 x 4 u16 influences, faces made with other
    tools 4 u8 (74651, 222790...); both index the same 400-bone skeleton."""
    return '<4B' if attr[2] == 'u8' else '<4H'


def convert_vertices(src, k, dst_decl, bone_map, fit=None, weights_of=None, offset=(0.0, 0.0, 0.0)):
    """FIFA 14 vertex buffer k -> FIFA Street vertex bytes (stride 32 layout of dst_decl). offset (cm) moves the
    positions onto the template's skeleton before anything else."""
    sd = decl(src, '<', k)
    o, _ = of_type(src, '<', VERTICES)[k]
    _, count, stride, _ = struct.unpack('<IIII', src[o:o + 16])
    out_stride = 32
    out = bytearray()
    for i in range(count):
        b = o + 16 + i * stride
        v = bytearray(out_stride)
        p = nrm = None
        for name, (doff, n, typ) in dst_decl.items():
            if name in ('i0', 'w0'):
                continue
            soff, sn, styp = sd[name]
            floats = ('f32', 'f16')
            if (sn, styp) != (n, typ) and not (styp in floats and typ in floats):
                raise ValueError(f'vertex attribute {name}: {sn}{styp} in the pack, {n}{typ} in the game')
            if (sn, styp) != (n, typ):
                # some packs store hair positions as 3 x f32 (the game: 4 x f16, w = 1)
                vals = struct.unpack_from(f'<{sn}{"f" if styp == "f32" else "e"}', src, b + soff)
                vals = (vals + (1.0,) * n)[:n]
                if name == 'p0':
                    vals = tuple(c + d for c, d in zip(vals, offset)) + vals[3:]
                    p = vals[:3]
                v[doff:doff + (4 if typ == 'f32' else 2) * n] = struct.pack(f'>{n}{"f" if typ == "f32" else "e"}', *vals)
            elif typ == 'f32':
                vals = struct.unpack_from(f'<{n}f', src, b + soff)
                if name == 'p0':
                    vals = tuple(c + d for c, d in zip(vals, offset))
                    if fit:
                        vals = fit(vals)
                    p = vals
                v[doff:doff + 4 * n] = struct.pack(f'>{n}f', *vals)
            elif typ == 'f16':
                vals = struct.unpack_from(f'<{n}e', src, b + soff)
                if name == 'p0':  # hair: 4 x f16 (x, y, z, w)
                    vals = tuple(c + d for c, d in zip(vals, offset)) + vals[3:]
                    p = vals[:3]
                v[doff:doff + 2 * n] = struct.pack(f'>{n}e', *vals)
            elif typ == 's10n':
                packed = struct.unpack_from('<I', src, b + soff)[0]
                if name == 'n0':
                    nrm = s10n(packed)
                v[doff:doff + 4] = struct.pack('>I', packed)
            else:
                raise ValueError(f'vertex attribute {name}: unknown format {typ}')
        weights = {}
        for iname, wname in (('i0', 'w0'), ('i1', 'w1')):
            if iname not in sd:
                continue
            idx = struct.unpack_from(_index_format(sd[iname]), src, b + sd[iname][0])
            ws = src[b + sd[wname][0]:b + sd[wname][0] + 4]
            for x, w in zip(idx, ws):
                if w:
                    weights[bone_map[x]] = weights.get(bone_map[x], 0) + w
        top = sorted(weights.items(), key=lambda kv: -kv[1])[:4]
        total = sum(w for _, w in top)
        scaled = [round(w * 255 / total) for _, w in top]
        scaled[0] += 255 - sum(scaled)
        idx = [bone for bone, _ in top] + [0] * (4 - len(top))
        scaled += [0] * (4 - len(scaled))
        copied = weights_of(p, nrm) if weights_of else None
        if copied:
            idx, scaled = copied
        v[dst_decl['i0'][0]:dst_decl['i0'][0] + 4] = bytes(idx)
        v[dst_decl['w0'][0]:dst_decl['w0'][0] + 4] = bytes(scaled)
        out += v
    return count, bytes(out)


def convert_indices(src, k):
    o, _ = of_type(src, '<', INDICES)[k]
    _, count = struct.unpack('<II', src[o:o + 8])
    if src[o + 8] != 2:
        raise ValueError('32-bit indices are not supported')
    return count, struct.pack(f'>{count}H', *struct.unpack_from(f'<{count}H', src, o + 16))


def rebuild(template, replace):
    """New RX3b from template with the given sections' contents replaced ({section index: bytes})."""
    secs = sections(template, '>')
    head_size = 16 + 16 * len(secs)
    first = min(o for _, o, _, _ in secs)
    body, table = bytearray(), []
    pos = first
    for i, (t, o, s, z) in enumerate(secs):
        data = replace.get(i, template[o:o + s])
        data = data + b'\0' * (-len(data) % 16)
        table.append(struct.pack('>IIII', t, pos, len(data), z))
        body += data
        pos += len(data)
    out = template[:12] + struct.pack('>I', len(secs)) + b''.join(table) + template[head_size:first] + body
    return bytearray(out[:8] + struct.pack('>I', len(out)) + out[12:])


def rename(template, sec_index, old, new):
    """Name section sec_index with old replaced by new in every entry. Ids of any length (an original player with a
    4-digit playerid gets Messi's files): the entries [type, length incl. NUL, text] are written again and the
    section is padded to 16 with its size field updated (rebuild moves the sections after it)."""
    o = sections(template, '>')[sec_index][1]
    count = struct.unpack('>I', template[o + 4:o + 8])[0]
    pos, body = o + 16, b''
    for _ in range(count):
        type_, n = struct.unpack('>II', template[pos:pos + 8])
        text = bytes(template[pos + 8:pos + 8 + n]).rstrip(b'\0').replace(old.encode(), new.encode())
        body += struct.pack('>II', type_, len(text) + 1) + text + b'\0'
        pos += 8 + n
    size = 16 + len(body)
    size += -size % 16
    return (struct.pack('>IIII', size, count, 0, 0) + body).ljust(size, b'\0')


def renamed(d, old, new):
    """RX3b d with its name section renamed (rename). The header's value at 8 is not the file size in every file
    (textures: less), so it keeps the original moved by the size change (same id length: d unchanged)."""
    k = next(i for i, s in enumerate(sections(d, '>')) if s[0] == NAMES)
    out = rebuild(d, {k: rename(d, k, old, new)})
    struct.pack_into('>I', out, 8, struct.unpack('>I', d[8:12])[0] + len(out) - len(d))
    return out


def convert_mesh(template, src, slot_of, old_id, new_id, fit_neck=False, offset=(0.0, 0.0, 0.0), vote=False,
                 empty=()):
    """slot_of[k] = template mesh index that receives FIFA 14 mesh k. offset: see align_offset. fit_neck: lay mesh
    0's neck base onto the template's (and take its weights below the chin); vote: bone map of mesh 0 by vote
    (vote_map; head mesh only). empty: template slots the face has nothing for (hair with a cap only): they get a
    single zero-area triangle, so none of the template's own geometry is left."""
    secs = sections(template, '>')
    idx_of = {t: [i for i, s in enumerate(secs) if s[0] == t] for t in (HEADER, NAMES, VERTICES, INDICES)}
    src_bones = [tuple(c + d for c, d in zip(b, offset)) for b in bone_positions(src, '<')]
    dst_bones = bone_positions(template, '>')
    replace = {}
    header = bytearray(template[secs[idx_of[HEADER][0]][1]:][:secs[idx_of[HEADER][0]][2]])
    for k, slot in enumerate(slot_of):
        dd = decl(template, '>', slot)
        allowed = sorted(used_bones(template, '>', slot, dd))
        bone_map = nearest_map(src_bones, dst_bones, allowed)
        if vote and k == 0:
            # the eyes align the head, but the mouths can sit a few mm apart: the mouth bones vote again with the
            # slits lined up (274254: -0.79 cm, which puts lower lip bones 75/87/91 on FS's lower lip)
            slit_tpl, slit_src = mouth_slit(template, '>', slot), mouth_slit(src, '<', k)
            dy = slit_tpl - (slit_src + offset[1])
            face_map = vote_map(src, k, template, slot, offset, bone_map)
            mouth_map = vote_map(src, k, template, slot, (offset[0], offset[1] + dy, offset[2]), bone_map)
            centers = {}
            for p, bw in vertex_bones(src, '<', k, decl(src, '<', k)):
                for x, w in bw.items():
                    c = centers.setdefault(x, [0.0, 0.0, 0.0])
                    c[0], c[1], c[2] = c[0] + p[1] * w, c[1] + p[2] * w, c[2] + w
            bone_map = {b: (mouth_map[b] if b in centers and abs(centers[b][0] / centers[b][2] - slit_src) < 2.5
                            and centers[b][1] / centers[b][2] > 3 else face_map[b]) for b in face_map}
        neck = fit_neck and k == 0
        fit = neck_fitter(template, slot) if neck else None
        weights_of = neck_weights(template, slot, dd) if neck else None
        count, vb = convert_vertices(src, k, dd, bone_map, fit, weights_of, offset)
        replace[idx_of[VERTICES][slot]] = struct.pack('>IIII', 16 + len(vb), count, 32, 0) + vb
        n_idx, ib = convert_indices(src, k)
        to = secs[idx_of[INDICES][slot]][1]
        replace[idx_of[INDICES][slot]] = struct.pack('>II', 16 + len(ib), n_idx) + template[to + 8:to + 16] + ib
        struct.pack_into('>II', header, 16 + 16 * slot, 16 + len(ib), n_idx)
    for slot in empty:
        vo = secs[idx_of[VERTICES][slot]][1]
        _, _, stride, _ = struct.unpack('>IIII', template[vo:vo + 16])
        vb = template[vo + 16:vo + 16 + stride] * 3
        replace[idx_of[VERTICES][slot]] = struct.pack('>IIII', 16 + len(vb), 3, stride, 0) + vb
        ib = struct.pack('>3H', 0, 1, 2)
        to = secs[idx_of[INDICES][slot]][1]
        replace[idx_of[INDICES][slot]] = struct.pack('>II', 16 + len(ib), 3) + template[to + 8:to + 16] + ib
        struct.pack_into('>II', header, 16 + 16 * slot, 16 + len(ib), 3)
    replace[idx_of[HEADER][0]] = bytes(header)
    replace[idx_of[NAMES][0]] = rename(template, idx_of[NAMES][0], old_id, new_id)
    return rebuild(template, replace)


def hair_parts(d):
    """{'cap': mesh index, 'strands': mesh index} of a hair RX3 by submesh name (alphaA = cap, alphaB = strands);
    packs differ in order and some hair has a cap only."""
    out = {}
    for k, m in enumerate(rx3mesh.meshes(d)):
        part = 'cap' if 'alphaA' in m['name'] else 'strands' if 'alphaB' in m['name'] else None
        if part and part not in out:
            out[part] = k
    return out


def rich_hairlod(template, src_lod, src_hair, old_id, new_id, offset, trim=0.01, share=0.6):
    """hairlod (far camera) stretched, axis by axis, onto the box of the body of the full hair (cap + strands).

    In play the game draws only the hairlod cap (player.lua, PlayerAssetLowLod; submesh alphaA). The FIFA 14 lod
    caps are 10-15% smaller than the full hair, so voluminous hair looked short from afar. Like EA's own lods
    (Puyol: 60-67% of the way from his near cap to his whole hair), the box goes `share` of the way from the near
    cap to the body of the hair, leaving out the `trim` outermost vertices on each side (thin strand tips).
    Cap UVs, opacity and the painted scalp are unchanged."""
    out = convert_mesh(template, src_lod, [0], old_id, new_id, offset=offset)
    parts = hair_parts(src_hair)
    full = [tuple(c + d for c, d in zip(p, offset)) for k in parts.values() for p in positions(src_hair, '<', k)]
    o, _ = of_type(out, '>', VERTICES)[0]
    _, count, stride, _ = struct.unpack('>IIII', out[o:o + 16])
    p0 = decl(out, '>', 0)['p0'][0]
    cap = [struct.unpack_from('>4e', out, o + 16 + i * stride + p0) for i in range(count)]
    lo = [min(p[k] for p in cap) for k in range(3)]
    hi = [max(p[k] for p in cap) for k in range(3)]
    near_cap = [tuple(c + d for c, d in zip(p, offset)) for p in positions(src_hair, '<', parts['cap'])]
    flo, fhi = [], []
    for k in range(3):
        v = sorted(p[k] for p in full)
        cut = int(trim * len(v))
        c_lo, c_hi = min(p[k] for p in near_cap), max(p[k] for p in near_cap)
        flo.append(c_lo + share * (min(v[cut], c_lo) - c_lo))
        fhi.append(c_hi + share * (max(v[len(v) - 1 - cut], c_hi) - c_hi))
    for i, p in enumerate(cap):
        q = [flo[k] + (p[k] - lo[k]) * (fhi[k] - flo[k]) / (hi[k] - lo[k]) for k in range(3)]
        struct.pack_into('>4e', out, o + 16 + i * stride + p0, *q, p[3])
    return out


def convert_textures(template, src, pairs, old_id, new_id):
    """pairs = [(template texture index, FIFA 14 texture index)]; copies raw pixels when format/size/mips match (the
    Xbox data is linear with bytes swapped in pairs, so the conversion is lossless); otherwise (HD packs with
    1024x1024 faces) the image is resized and re-encoded in the template's format and size."""
    out = bytearray(template)
    tt, st = of_type(template, '>', TEXTURE), of_type(src, '<', TEXTURE)
    for ti, si in pairs:
        to, ts = tt[ti]
        so, ss = st[si]
        th = struct.unpack('>IBBBBHHHH', template[to:to + 16])
        sh = struct.unpack('<IBBHHHHH', src[so:so + 16])
        if (th[2], th[5], th[6], th[8]) != (sh[2], sh[4], sh[5], sh[7]):
            image = rx3tex.to_image(src, rx3tex.textures(src)[si]).convert('RGBA')
            rx3tex.set_image(out, rx3tex.textures(out)[ti], image)
            continue
        q, r = to + 16, so + 16
        for _ in range(th[8]):
            mt = struct.unpack('>IIII', template[q:q + 16])
            ms = struct.unpack('<IIII', src[r:r + 16])
            if mt != ms:
                raise ValueError(f'texture {ti}: mip levels differ')
            out[q + 16:q + 16 + mt[2]] = rx3tex.swap16(src[r + 16:r + 16 + ms[2]])
            q, r = q + 16 + mt[2], r + 16 + ms[2]
    return renamed(out, old_id, new_id)


def paint_scalp(face, head, hair, hair_tex, color, res=256, reach=3.0):
    """Paints the hair onto the scalp of the face texture (all RX3b, face is changed in place).

    FIFA Street face textures carry the hair painted on the scalp and the hair cap (alphaA, opacity = hair_coeff R
    at UV 0) is blended over it; FIFA 14 scalps are bare skin, so wherever the cap is not fully opaque (edges, the
    nape, the far-camera hairlod) the game shows skin. For each texel of the head mesh (texture space, res²), the
    nearest cap vertex within `reach` cm and outside the skin (60° around the normal) gives the opacity and the
    hair_cm shade; the result is blurred, scaled to the texture and blended with the hair color (hex RGB)."""
    head_mesh = [m for m in rx3mesh.meshes(head) if 'eyes' not in m['name']][0]
    cap = [m for m in rx3mesh.meshes(hair) if 'alphaA' in m['name']][0]
    coeff = rx3tex.to_image(hair_tex, rx3tex.textures(hair_tex)[0]).convert('RGBA')
    shade = rx3tex.to_image(hair_tex, rx3tex.textures(hair_tex)[1]).convert('L')
    cpx, spx = coeff.load(), shade.load()
    cells = {}
    for p, uv in zip(cap['attrs']['p0'], cap['attrs']['t0']):
        u, v = uv[0] % 1, uv[1] % 1
        hit = (cpx[int(u * coeff.width), int(v * coeff.height)][0], spx[int(u * shade.width), int(v * shade.height)])
        cells.setdefault(tuple(int(c // reach) for c in p[:3]), []).append((p[:3], hit))

    def nearest(p, n):
        best, hit = reach * reach, None
        cx, cy, cz = (int(c // reach) for c in p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q, h in cells.get((cx + dx, cy + dy, cz + dz), ()):
                        o = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
                        d = o[0] ** 2 + o[1] ** 2 + o[2] ** 2
                        # the cap must lie outside the skin (along the normal), not beside it (forehead below
                        # the hairline)
                        if d < best and o[0] * n[0] + o[1] * n[1] + o[2] * n[2] > 0.5 * d ** 0.5:
                            best, hit = d, h
        return hit

    alpha, tone = Image.new('L', (res, res), 0), Image.new('L', (res, res), 0)
    apx, tpx = alpha.load(), tone.load()
    pos, uvs, idx = head_mesh['attrs']['p0'], head_mesh['attrs']['t0'], head_mesh['indices']
    nrm = head_mesh['attrs']['n0']
    for t in range(0, len(idx) - 2, 3):
        tri = idx[t:t + 3]
        (x0, y0), (x1, y1), (x2, y2) = ((uvs[i][0] * res, uvs[i][1] * res) for i in tri)
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if not area:
            continue
        for y in range(max(0, int(min(y0, y1, y2))), min(res - 1, int(max(y0, y1, y2))) + 1):
            for x in range(max(0, int(min(x0, x1, x2))), min(res - 1, int(max(x0, x1, x2))) + 1):
                w0 = ((x1 - x - .5) * (y2 - y - .5) - (x2 - x - .5) * (y1 - y - .5)) / area
                w1 = ((x2 - x - .5) * (y0 - y - .5) - (x0 - x - .5) * (y2 - y - .5)) / area
                w2 = 1 - w0 - w1
                if min(w0, w1, w2) < -0.02:
                    continue
                p = [w0 * pos[tri[0]][k] + w1 * pos[tri[1]][k] + w2 * pos[tri[2]][k] for k in range(3)]
                n = [w0 * nrm[tri[0]][k] + w1 * nrm[tri[1]][k] + w2 * nrm[tri[2]][k] for k in range(3)]
                ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1
                hit = nearest(p, [c / ln for c in n])
                if hit:
                    apx[x, y], tpx[x, y] = hit
    t = rx3tex.textures(face)[0]
    img = rx3tex.to_image(face, t).convert('RGB')
    size = img.size
    alpha = alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.5)).resize(size, Image.BILINEAR)
    tone = tone.filter(ImageFilter.MaxFilter(3)).resize(size, Image.BILINEAR)
    r, g, b = (int(color.lstrip('#')[k:k + 2], 16) for k in (0, 2, 4))
    hair = Image.merge('RGB', [tone.point(lambda v, c=c: min(255, int(c * (0.5 + v / 255)))) for c in (r, g, b)])
    rx3tex.set_image(face, t, Image.composite(hair, img, alpha))
    return face


def scalp(head):
    """Function q -> (height of q above the head's skin along the normal of the nearest head vertex, that normal), or
    None when no head vertex lies within ~4 cm (head: converted RX3b)."""
    head_mesh = [m for m in rx3mesh.meshes(head) if 'eyes' not in m['name']][0]
    pos = [p[:3] for p in head_mesh['attrs']['p0']]
    nrm = [tuple(c / (math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1) for c in n[:3]) for n in head_mesh['attrs']['n0']]
    grid = {}
    for i, p in enumerate(pos):
        grid.setdefault(tuple(int(c // 2) for c in p), []).append(i)

    def height(q):
        cx, cy, cz = (int(c // 2) for c in q)
        best = None
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for dz in (-2, -1, 0, 1, 2):
                    for i in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        d = (q[0] - pos[i][0]) ** 2 + (q[1] - pos[i][1]) ** 2 + (q[2] - pos[i][2]) ** 2
                        if best is None or d < best[0]:
                            best = (d, i)
        if best is None:
            return None
        i = best[1]
        return sum((q[j] - pos[i][j]) * nrm[i][j] for j in range(3)), nrm[i]
    return height


def cap_to_scalp(hair, head, gap=CAP_GAP, smooth=CAP_SMOOTH):
    """Moves the cap (alphaA) vertices of a converted hair (RX3b, changed in place) along the scalp normal so none is
    more than `gap` cm above the head's skin; the strands (alphaB) are not touched. The pull of each vertex (to the
    nearest head vertex) is averaged with its neighbors `smooth` times. Validated in game with face 71654 (24/10)."""
    k = hair_parts(hair)['cap']
    cap = rx3mesh.meshes(hair)[k]
    height = scalp(head)
    pts = [p[:3] for p in cap['attrs']['p0']]
    pull = []
    for q in pts:
        hit = height(q)
        if hit is None:
            pull.append((0.0, 0.0, 0.0))
            continue
        d, n = hit
        pull.append(tuple(-(d - gap) * n[j] for j in range(3)) if d > gap else (0.0, 0.0, 0.0))
    neighbors = [set() for _ in pts]
    idx = cap['indices']
    for t in range(0, len(idx) - 2, 3):
        a, b, c = idx[t:t + 3]
        neighbors[a].update((b, c))
        neighbors[b].update((a, c))
        neighbors[c].update((a, b))
    for _ in range(smooth):
        pull = [tuple((pull[i][j] + sum(pull[n][j] for n in neighbors[i])) / (1 + len(neighbors[i])) for j in range(3))
                for i in range(len(pts))]
    o, _ = of_type(hair, '>', VERTICES)[k]
    _, count, stride, _ = struct.unpack('>IIII', hair[o:o + 16])
    off, _, typ = decl(hair, '>', k)['p0']
    fmt = '>3f' if typ == 'f32' else '>3e'
    for i in range(count):
        at = o + 16 + i * stride + off
        x, y, z = struct.unpack_from(fmt, hair, at)
        struct.pack_into(fmt, hair, at, x + pull[i][0], y + pull[i][1], z + pull[i][2])
    return hair


def _buffers(d, k):
    """(vertex records, indices) of mesh k of an RX3b."""
    o, _ = of_type(d, '>', VERTICES)[k]
    _, count, stride, _ = struct.unpack('>IIII', d[o:o + 16])
    verts = [bytes(d[o + 16 + i * stride:o + 16 + (i + 1) * stride]) for i in range(count)]
    o, _ = of_type(d, '>', INDICES)[k]
    n = struct.unpack('>I', d[o + 4:o + 8])[0]
    return verts, list(struct.unpack_from(f'>{n}H', d, o + 16))


def _with_buffers(d, meshes):
    """New RX3b from d with the vertex records and indices of some meshes replaced ({mesh: (verts, indices)})."""
    secs = sections(d, '>')
    idx_of = {t: [i for i, s in enumerate(secs) if s[0] == t] for t in (HEADER, VERTICES, INDICES)}
    header = bytearray(d[secs[idx_of[HEADER][0]][1]:][:secs[idx_of[HEADER][0]][2]])
    replace = {}
    for k, (verts, indices) in meshes.items():
        if len(verts) > 0xFFFF:
            raise ValueError('hair mesh with more than 65535 vertices')
        vb = b''.join(verts)
        replace[idx_of[VERTICES][k]] = struct.pack('>IIII', 16 + len(vb), len(verts), len(verts[0]), 0) + vb
        ib = struct.pack(f'>{len(indices)}H', *indices)
        to = secs[idx_of[INDICES][k]][1]
        replace[idx_of[INDICES][k]] = struct.pack('>II', 16 + len(ib), len(indices)) + d[to + 8:to + 16] + ib
        struct.pack_into('>II', header, 16 + 16 * k, 16 + len(ib), len(indices))
    replace[idx_of[HEADER][0]] = bytes(header)
    return rebuild(d, replace)


def split_cap(hair, head, keep_strands, reach=SPLIT_REACH):
    """New hair RX3b whose cap (alphaA) keeps only the triangles lying on the scalp (every vertex at most `reach` cm
    above the skin); the others go to the strands slot (alphaB), after the pack's own strands when keep_strands.

    Some packs model the whole hair as a single "cap" mesh of curl cards (Hugo Souza 276570, ~5% of the faces). As a
    cap it is drawn one-sided, its opacity comes from hair_coeff R (half grey on those atlases) and the pull flattens
    its curls onto the skin; as strands the cards are seen from both sides, use hair_coeff B and keep their volume."""
    parts = hair_parts(hair)
    height = scalp(head)
    cap_verts, cap_idx = _buffers(hair, parts['cap'])
    up = []
    for p in rx3mesh.meshes(hair)[parts['cap']]['attrs']['p0']:
        hit = height(p[:3])
        up.append(math.inf if hit is None else hit[0])
    keep, move = [], []
    for t in range(0, len(cap_idx) - 2, 3):
        tri = cap_idx[t:t + 3]
        (move if max(up[i] for i in tri) > reach else keep).append(tri)
    if not keep or not move:
        return hair

    def gather(verts, indices, tris):
        remap = {}
        for tri in tris:
            for i in tri:
                if i not in remap:
                    remap[i] = len(verts)
                    verts.append(cap_verts[i])
                indices.append(remap[i])
        return verts, indices
    strands = _buffers(hair, parts['strands']) if keep_strands else ([], [])
    return _with_buffers(hair, {parts['cap']: gather([], [], keep), parts['strands']: gather(*strands, move)})


def _texture_section(d, t):
    return [i for i, s in enumerate(sections(d, '>')) if s[0] == TEXTURE and s[1] == t['off']][0]


def resize_texture(d, t, w, h):
    """New RX3b with texture t (rx3tex.textures entry, DXT) reallocated at w x h with a full mip chain (zeroed; fill
    it with rx3tex.set_image). The texture header list (section 0x6BD085DC) gets the new header too."""
    block = 8 if t['fmt'] == 0 else 16
    mips = max(w, h).bit_length()
    body = b''
    for m in range(mips):
        pitch, rows = max(1, ((w >> m) + 3) // 4) * block, max(1, ((h >> m) + 3) // 4)
        body += struct.pack('>IIII', pitch, rows, pitch * rows, 0) + bytes(pitch * rows)
    body += bytes(-len(body) % 16)  # section sizes are multiples of 16
    head = struct.pack('>IBBBBHHHH', 16 + len(body), 1, t['fmt'], 3, 0, w, h, 1, mips)
    replace = {_texture_section(d, t): head + body}
    secs = sections(d, '>')
    for i, (type_, o, s, _) in enumerate(secs):
        if type_ == TEXTURE_HEADERS:
            n = [x for x in rx3tex.textures(d)].index(t)
            replace[i] = d[o:o + 16 + 16 * n] + head + d[o + 32 + 16 * n:o + s]
    return rebuild(d, replace)


def sharp_textures(tex, src_tex, limit=SHARP_MAX):
    """New hair textures RX3b with hair_coeff and hair_cm at the pack's resolution (largest side at most `limit`)
    instead of the template's 256/512: curl atlases 2048 px wide squeezed into 256 turn the curls into a blur."""
    for name in ('hair_coeff', 'hair_cm'):
        t, s = rx3tex.by_name(tex, name), rx3tex.by_name(src_tex, name)
        scale = min(1.0, limit / max(s['w'], s['h']))
        w, h = int(s['w'] * scale), int(s['h'] * scale)
        if w * h <= t['w'] * t['h']:
            continue
        image = rx3tex.to_image(src_tex, s).convert('RGBA')
        tex = resize_texture(tex, t, w, h)
        rx3tex.set_image(tex, rx3tex.by_name(tex, name), image)
    return tex


def dense_coeff(tex):
    """hair_coeff R (cap opacity) raised to B (strands opacity), texel by texel (tex changed in place). Single-mesh
    hair keeps its full opacity in B and only a half grey in R."""
    t = rx3tex.by_name(tex, 'hair_coeff')
    r, g, b, a = rx3tex.to_image(tex, t).convert('RGBA').split()
    rx3tex.set_image(tex, t, Image.merge('RGBA', (ImageChops.lighter(r, b), g, b, a)))
    return tex


def thick_coeff(tex, gamma=THICK_GAMMA):
    """hair_coeff R and B (opacities) raised to the power `gamma` < 1 (tex changed in place): the soft edges of each
    strand get more opaque, so the sharp curl atlas looks as full as the blurred one, zero stays zero. In game the
    sharp texture kept the back of the hair but its curls looked thinner than with the template's 256 px (28/10)."""
    t = rx3tex.by_name(tex, 'hair_coeff')
    r, g, b, a = rx3tex.to_image(tex, t).convert('RGBA').split()
    curve = [round(255 * (v / 255) ** gamma) for v in range(256)]
    rx3tex.set_image(tex, t, Image.merge('RGBA', (r.point(curve), g, b.point(curve), a)))
    return tex


def align_offset(template_head, src_head):
    """Offset (cm) that puts the FIFA 14 head on the template's skeleton: FIFA 14 skeletons carry the head 3-4 cm
    further forward (head bone z=4.1 x 0 in FIFA Street), so the converted face sat in front of the body's neck
    bones and the bone mapping picked wrong facial bones. Uses the eyes (mesh 1) as landmark: bbox centers."""
    def center(pts):
        return [(min(p[k] for p in pts) + max(p[k] for p in pts)) / 2 for k in range(3)]
    a, b = center(positions(template_head, '>', 1)), center(positions(src_head, '<', 1))
    return (0.0, a[1] - b[1], a[2] - b[2])  # x stays 0: heads are symmetric


def template_files(sources, template=TEMPLATE):
    """{kind: RX3b bytes} of the template's scanned head in the original game files."""
    out = {}
    for kind, name in FILES.items():
        entry = sources.read_entry(ASSETS + name.format(template))
        if entry is None:
            raise KeyError(name.format(template))
        out[kind] = bytearray(chunk.decode(entry[2]))
    return out


def game_files(sources, playerid):
    """{kind: RX3b bytes} of one of the game's own scanned heads (the kinds it has), e.g. for the preview."""
    out = {}
    for kind, name in FILES.items():
        entry = sources.read_entry(ASSETS + name.format(playerid))
        if entry is not None:
            out[kind] = bytearray(chunk.decode(entry[2]))
    return out


def convert(tpl, src, new_id, hair_color, template=TEMPLATE, paint=True, hair_mode='standard',
            hair_thickness=HAIR_THICKNESS):
    """FIFA Street files {asset name relative to data/sceneassets: RX3b bytes} of a FIFA 14 face.

    tpl: template_files(); src: {kind: RX3l bytes} of the pack (REQUIRED kinds, optional hair/hair_textures/
    hairlod); new_id: playerassetid of the result (any number of digits); hair_color: '#rrggbb'
    painted on the scalp (preview.hair_color(haircolorcode)); paint=False skips that (ScannedFace.paint_scalp). Eyes: the template's eyeball (FIFA Street slides it
    to move the gaze; some packs bring a photo of the eye with lids, which turned into "eyes rolled back").
    hair_mode: key of HAIR_MODES (ScannedFace.hair_mode); hair_thickness: 0..HAIR_THICKNESS_MAX, used by the 'thick'
    step (ScannedFace.hair_thickness)."""
    missing = [k for k in REQUIRED if not src.get(k)]
    if missing:
        raise ValueError(f'missing face files: {", ".join(missing)}')
    if hair_mode not in HAIR_MODES:
        raise ValueError(f'unknown hair mode: {hair_mode}')
    steps = HAIR_MODES[hair_mode]
    if not 0 <= hair_thickness <= HAIR_THICKNESS_MAX:
        raise ValueError(f'hair thickness out of range: {hair_thickness}')
    old, new = str(template), str(new_id)
    name = {kind: f.format(new) for kind, f in FILES.items()}
    offset = align_offset(tpl['head'], src['head'])
    files = {name['head']: convert_mesh(tpl['head'], src['head'], [0, 1], old, new, True, offset, vote=True),
             name['face']: convert_textures(tpl['face'], src['face'], [(0, 0)], old, new)}
    files[name['eyes']] = renamed(tpl['eyes'], old, new)
    hair = src.get('hair') if src.get('hair_textures') else None
    if hair and 'cap' not in hair_parts(hair):
        raise ValueError('hair without a cap (alphaA)')
    if hair:
        # template slots by name (Messi: 0 = strands alphaB, 1 = cap alphaA); a face without strands empties theirs
        tpl_parts, src_parts = hair_parts(tpl['hair']), hair_parts(hair)
        slot_of = [None] * len(rx3mesh.meshes(hair))
        for part, k in src_parts.items():
            slot_of[k] = tpl_parts[part]
        if None in slot_of:
            raise ValueError('hair submesh that is neither cap nor strands')
        empty = [tpl_parts[p] for p in tpl_parts if p not in src_parts]
        files[name['hair']] = convert_mesh(tpl['hair'], hair, slot_of, old, new, offset=offset, empty=empty)
        files[name['hair_textures']] = convert_textures(tpl['hair_textures'], src['hair_textures'],
                                                        [(0, 0), (1, 1)], old, new)
        if 'sharp' in steps:
            files[name['hair_textures']] = sharp_textures(files[name['hair_textures']], src['hair_textures'])
        if 'dense' in steps and 'strands' not in src_parts:
            dense_coeff(files[name['hair_textures']])
    if src.get('hairlod'):  # low-detail cap used in normal play (far camera); lives in data7
        # some packs mark "no far hair" with a 1 cm placeholder quad inside the head (215421): never stretched
        lod = positions(src['hairlod'], '<', 0)
        placeholder = max(max(q[k] for q in lod) - min(q[k] for q in lod) for k in range(3)) < 3
        files[name['hairlod']] = (rich_hairlod(tpl['hairlod'], src['hairlod'], hair, old, new, offset)
                                  if hair and not placeholder else
                                  convert_mesh(tpl['hairlod'], src['hairlod'], [0], old, new, offset=offset))
    if hair and paint:
        paint_scalp(files[name['face']], files[name['head']], files[name['hair']], files[name['hair_textures']],
                    hair_color)
    if hair and 'thick' in steps:  # after the paint: thicker strands must not spread the scalp paint
        thick_coeff(files[name['hair_textures']], 1 - hair_thickness)
    if hair and 'split' in steps:
        files[name['hair']] = split_cap(files[name['hair']], files[name['head']], 'strands' in src_parts)
    if hair and 'pull' in steps and CAP_GAP is not None:
        # after the paint, like the game test (the paint looks for the original cap)
        cap_to_scalp(files[name['hair']], files[name['head']])
    return {k: bytes(v) for k, v in files.items()}
