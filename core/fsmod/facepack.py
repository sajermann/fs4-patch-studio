"""FIFA 14 face packs (e.g. soccergaming.com) on the user's disk: listing, reading and gallery thumbnails.

A pack folder holds screenassets/ (heads/, faces/, hair/, hairlod/: see scanface.FILES) and often
ui/imgAssets/heads/p<id>.dds (player photos), or the same folders straight in the pack root, without screenassets/
(both layouts work). The user may point at the pack root, at screenassets itself or at a folder with one pack inside. Packs are read in place and never written; the app never ships packs.
The pack's database is the PC version (compressed names that fsmod.t3db does not read), so the ids say nothing
about who the player is: the gallery shows each face rendered from the front.
"""
import io
import os
import re

from PIL import Image

from . import rx3mesh, rx3tex
from .scanface import FILES, REQUIRED, read_files

SCREENASSETS = 'screenassets'
PHOTOS = os.path.join('ui', 'imgAssets', 'heads')
FACE_RE = re.compile(r'face_(\d+)_0_0_0_0_0_0_0_0_textures\.rx3$')


def assets_dir(folder):
    """screenassets folder of a pack (the folder itself, its child, or the child of its only subfolder), or None."""
    if not folder or not os.path.isdir(folder):
        return None
    candidates = [folder, os.path.join(folder, SCREENASSETS)]
    try:
        subs = [e.path for e in os.scandir(folder) if e.is_dir()]
    except OSError:  # no permission
        return None
    if len(subs) == 1:
        candidates.append(os.path.join(subs[0], SCREENASSETS))
    for c in candidates:
        if os.path.isdir(os.path.join(c, 'heads')) and os.path.isdir(os.path.join(c, 'faces')):
            return c
    return None


def pack_root(assets):
    """The pack's own folder: the parent of screenassets/, or assets itself when the pack has no screenassets/."""
    return os.path.dirname(assets) if os.path.basename(os.path.normpath(assets)).lower() == SCREENASSETS else assets


def pack_name(assets):
    """Name of the pack (its folder name), whichever the layout."""
    return os.path.basename(os.path.normpath(pack_root(assets)))


def _photo_path(assets, face_id):
    return os.path.join(pack_root(assets), PHOTOS, f'p{face_id}.dds')


def list_faces(assets):
    """[{'id', 'hair', 'hairlod', 'photo'}] of the complete faces (head mesh + face texture), by id."""
    names = {kind: set(os.listdir(os.path.join(assets, os.path.dirname(f))))
             for kind, f in FILES.items() if os.path.isdir(os.path.join(assets, os.path.dirname(f)))}
    out = []
    for n in names.get('face', ()):
        m = FACE_RE.match(n)
        if not m:
            continue
        fid = int(m[1])
        has = {kind: os.path.basename(f.format(fid)) in names.get(kind, ()) for kind, f in FILES.items()}
        if all(has[k] for k in REQUIRED):
            out.append({'id': fid, 'hair': has['hair'] and has['hair_textures'], 'hairlod': has['hairlod'],
                        'photo': os.path.isfile(_photo_path(assets, fid))})
    return sorted(out, key=lambda f: f['id'])


def read_face(assets, face_id):
    """{kind: RX3l bytes} of the files a face has in the pack."""
    return read_files(assets, face_id)


def photo(assets, face_id):
    """Player photo shipped with the pack (PIL image) or None."""
    path = _photo_path(assets, face_id)
    if not os.path.isfile(path):
        return None
    try:
        return Image.open(path).convert('RGBA')
    except OSError:
        return None


# ------------------------------------------------------------------ thumbnail (front view, PIL only)

FRAME = (-15.0, 150.5, 15.0, 186.5)  # cm (x0, y0, x1, y1) around the head in the reference pose
LIGHT = (0.35, 0.45, 0.82)  # towards the viewer, from the upper left
BACKGROUND = (0, 0, 0, 0)


def _texture(d, index):
    return rx3tex.to_image(d, rx3tex.textures(d)[index]).convert('RGBA')


def _shade(n):
    ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1
    return 0.45 + 0.65 * max(0.0, (n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]) / ln)


def _draw(out, zbuf, size, mesh, tex, alpha=None, uv_alpha='t0', tint=(1.0, 1.0, 1.0)):
    """Rasterizes mesh (orthographic, front) with z-buffer, per-vertex light and optional alpha test (alpha =
    (grey image, threshold) sampled with the uv_alpha set)."""
    x0, y0, x1, y1 = FRAME
    sx, sy = size / (x1 - x0), size / (y1 - y0)
    a = mesh['attrs']
    pts = [((p[0] - x0) * sx, (y1 - p[1]) * sy, p[2]) for p in a['p0']]
    uv, uva = a['t0'], a.get(uv_alpha, a['t0'])
    light = [_shade(n) for n in a['n0']] if 'n0' in a else [1.0] * len(pts)
    px, (tw, th) = tex.load(), tex.size
    if alpha:
        apx, (aw, ah), cut = alpha[0].load(), alpha[0].size, alpha[1]
    idx = mesh['indices']
    for t in range(0, len(idx) - 2, 3):
        i0, i1, i2 = idx[t:t + 3]
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[i0], pts[i1], pts[i2]
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area == 0:
            continue
        inv = 1.0 / area
        for y in range(max(0, int(min(ay, by, cy))), min(size - 1, int(max(ay, by, cy))) + 1):
            fy = y + 0.5
            for x in range(max(0, int(min(ax, bx, cx))), min(size - 1, int(max(ax, bx, cx))) + 1):
                fx = x + 0.5
                w0 = ((bx - fx) * (cy - fy) - (cx - fx) * (by - fy)) * inv
                w1 = ((cx - fx) * (ay - fy) - (ax - fx) * (cy - fy)) * inv
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * az + w1 * bz + w2 * cz
                k = y * size + x
                if z <= zbuf[k]:
                    continue
                if alpha:
                    u = w0 * uva[i0][0] + w1 * uva[i1][0] + w2 * uva[i2][0]
                    v = w0 * uva[i0][1] + w1 * uva[i1][1] + w2 * uva[i2][1]
                    if apx[int(u % 1 * aw), int(v % 1 * ah)] < cut:
                        continue
                u = w0 * uv[i0][0] + w1 * uv[i1][0] + w2 * uv[i2][0]
                v = w0 * uv[i0][1] + w1 * uv[i1][1] + w2 * uv[i2][1]
                c = px[int(u % 1 * tw), int(v % 1 * th)]
                s = w0 * light[i0] + w1 * light[i1] + w2 * light[i2]
                zbuf[k] = z
                out[x, y] = (min(255, int(c[0] * s * tint[0])), min(255, int(c[1] * s * tint[1])),
                             min(255, int(c[2] * s * tint[2])), 255)


def thumbnail(files, size=160, hair_tint=0.9):
    """PNG of a face seen from the front: head with its face texture, eyes, hair (cap + strands, alpha tested).
    files: {kind: RX3 bytes} (pack or converted). hair_tint: the game draws scanned hair with hairColor 0x808080
    (the viewer's gain makes it ~0.9)."""
    img = Image.new('RGBA', (size, size), BACKGROUND)
    out, zbuf = img.load(), [-1e9] * (size * size)
    face = _texture(files['face'], 0)
    # some packs have no eyes file (the build uses the template's eyeball): dark eyes instead of holes
    eyes = _texture(files['eyes'], 0) if files.get('eyes') else Image.new('RGBA', (4, 4), (55, 42, 34, 255))
    for m in rx3mesh.meshes(files['head']):
        _draw(out, zbuf, size, m, eyes if 'eyes' in m['name'] else face)
    if files.get('hair') and files.get('hair_textures'):
        coeff, cm = _texture(files['hair_textures'], 0), _texture(files['hair_textures'], 1)
        cap_alpha, strands_alpha = coeff.getchannel('R'), coeff.getchannel('B')
        tint = (hair_tint,) * 3
        for m in rx3mesh.meshes(files['hair']):
            if 'alphaA' in m['name']:  # the coeff is read with the second UV set, like the game (preview.HAIR_PARTS)
                _draw(out, zbuf, size, m, cm, (cap_alpha, 110), 't1', tint)
            else:
                _draw(out, zbuf, size, m, cm, (strands_alpha, 110), 't1', tint)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
