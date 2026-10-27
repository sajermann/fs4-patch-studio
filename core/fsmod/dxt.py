"""DXT1 (BC1) encoder with numpy, better than Pillow's on hard edges (in game, Pillow left a light,
blocky halo around a dark crest on a yellow jersey).

Per 4x4 block: endpoints from the bounding box and from the colors' principal axis (power iteration), the best
of the two, then up to two least-squares refinements of the endpoints for the chosen indices. Always 4-color mode
(c0 > c1). Output = linear blocks as in a DDS file (little-endian; rx3tex swaps them for the Xbox files).
"""
import numpy as np

WEIGHTS = np.array([1.0, 0.0, 2 / 3, 1 / 3], dtype=np.float32)  # weight of c0 for index 0..3


def _blocks(img):
    """(rows of blocks, columns of blocks, N x 16 x 3 float32) of a PIL image; sizes padded to multiples of 4."""
    a = np.asarray(img.convert('RGB'), dtype=np.float32)
    h, w = a.shape[:2]
    bh, bw = -(-h // 4), -(-w // 4)
    if (bh * 4, bw * 4) != (h, w):
        a = np.pad(a, ((0, bh * 4 - h), (0, bw * 4 - w), (0, 0)), mode='edge')
    blocks = a.reshape(bh, 4, bw, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3)
    return bh, bw, blocks


def _to565(c):
    q = np.clip(np.rint(c), 0, 255)
    r = (q[:, 0] * 31 + 127) // 255
    g = (q[:, 1] * 63 + 127) // 255
    b = (q[:, 2] * 31 + 127) // 255
    return (r.astype(np.int32) << 11) | (g.astype(np.int32) << 5) | b.astype(np.int32)


def _from565(v):
    r, g, b = v >> 11, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], axis=-1).astype(np.float32)


def _fit(px, e0, e1):
    """(error, c0, c1, indices) of every block for endpoints e0/e1 (N x 3)."""
    a, b = _to565(e0), _to565(e1)
    a, b = np.maximum(a, b), np.minimum(a, b)
    same = a == b  # 4-color mode needs c0 > c1: move one endpoint by one step (index 0 still = the color)
    b = np.where(same & (a > 0), a - 1, b)
    a = np.where(same & (a == 0), 1, a)
    p0, p1 = _from565(a), _from565(b)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], axis=1)  # N x 4 x 3
    d = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)  # N x 16 x 4
    idx = d.argmin(-1)
    err = np.take_along_axis(d, idx[..., None], -1)[..., 0].sum(-1)
    return err, a, b, idx


def _refine(px, idx):
    """Least-squares endpoints for fixed indices (N x 3 each) and a mask of the blocks where it is defined."""
    w = WEIGHTS[idx]  # N x 16
    v = 1 - w
    aa, bb, ab = (w * w).sum(1), (v * v).sum(1), (w * v).sum(1)
    ax, bx = (w[..., None] * px).sum(1), (v[..., None] * px).sum(1)
    det = aa * bb - ab * ab
    ok = np.abs(det) > 1e-6
    det = np.where(ok, det, 1)
    e0 = (bb[:, None] * ax - ab[:, None] * bx) / det[:, None]
    e1 = (aa[:, None] * bx - ab[:, None] * ax) / det[:, None]
    return e0, e1, ok


def _keep_better(best, cand, mask=None):
    better = cand[0] < best[0]
    if mask is not None:
        better &= mask
    return tuple(np.where(better[:, None] if x.ndim == 2 else better, y, x) for x, y in zip(best, cand))


def encode(img):
    """DXT1 data of a PIL image (blocks in rows, as in a DDS file)."""
    _, _, px = _blocks(img)
    lo, hi = px.min(1), px.max(1)
    best = _fit(px, hi, lo)
    mean = px.mean(1)
    centered = px - mean[:, None, :]
    cov = np.einsum('nki,nkj->nij', centered, centered)
    axis = hi - lo
    axis = np.where(np.abs(axis).sum(1, keepdims=True) > 0, axis, 1)
    for _ in range(4):
        axis = np.einsum('nij,nj->ni', cov, axis)
        axis /= np.maximum(np.abs(axis).max(1, keepdims=True), 1e-6)
    norm = np.maximum((axis * axis).sum(1), 1e-6)
    proj = np.einsum('nki,ni->nk', centered, axis) / norm[:, None]
    best = _keep_better(best, _fit(px, mean + axis * proj.max(1)[:, None], mean + axis * proj.min(1)[:, None]))
    for _ in range(2):
        e0, e1, ok = _refine(px, best[3])
        best = _keep_better(best, _fit(px, e0, e1), ok)
    _, a, b, idx = best
    bits = (idx.astype(np.uint32) << (2 * np.arange(16, dtype=np.uint32))).sum(1, dtype=np.uint32)
    out = np.zeros(len(px), dtype=[('c0', '<u2'), ('c1', '<u2'), ('bits', '<u4')])
    out['c0'], out['c1'], out['bits'] = a, b, bits
    return out.tobytes()
