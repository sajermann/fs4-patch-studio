"""Meshes inside RX3b files (Xbox 360, big-endian): generic heads and hair. RX3l files (PC, little-endian, e.g.
FIFA 14 face packs) have the same sections and are read the same way.

Sections (u32 type, offset, size, 0 in the RX3b table):
  0xC28193F0  vertex declaration, text after a 16-byte header, e.g.
              'p0:00:00:0001:3f32 n0:0C:00:0001:3s10n t0:14:00:0001:2f16 i0:18:00:0001:4u8 w0:1C:00:0001:4u8n'
              = attribute:offset(hex):?:?:count+type (f32, f16, s10n = 10:10:10 signed normalized, u8, u8n)
  0x00587AA1  vertices: u32 size | u32 count | u32 stride | u32 0 + data
  0x005878F4  indices: u32 size | u32 count | u8 index size | 7 bytes + u16 BE, triangle list
  0xDF9AEC1E  bone matrices, 0x0F3861A2 / 0xD48D7880 material/parts (not decoded), 0x4C9B9EB2 names.
The n-th declaration, vertex and index sections form the n-th mesh. Positions are in cm (head between y=148
and 184).
"""
import struct

DECL, VERTICES, INDICES, NAMES = 0xC28193F0, 0x00587AA1, 0x005878F4, 0x4C9B9EB2


def endian(d):
    """struct byte order of an RX3 file: '<' for RX3l (PC), '>' for RX3b (Xbox 360)."""
    return '<' if d[:4] == b'RX3l' else '>'


def _sections(d):
    e = endian(d)
    n = struct.unpack(e + 'I', d[12:16])[0]
    return [struct.unpack(e + 'IIII', d[16 + 16 * i:32 + 16 * i]) for i in range(n)]


def _decl(b):
    out = []
    for tok in b[16:].split(b'\0')[0].decode('ascii').split():
        name, off, _, _, fmt = tok.split(':')
        out.append((name, int(off, 16), int(fmt[0]), fmt[1:]))
    return out


def _s10n(v):
    out = []
    for k in range(3):
        x = (v >> (10 * k)) & 0x3FF
        out.append((x - 0x400 if x & 0x200 else x) / 511.0)
    return out


def _read(raw, count, stride, off, n, typ, e='>'):
    if typ == 'f32':
        f = struct.Struct(f'{e}{n}f')
        return [list(f.unpack_from(raw, i * stride + off)) for i in range(count)]
    if typ == 'f16':
        f = struct.Struct(f'{e}{n}e')
        return [list(f.unpack_from(raw, i * stride + off)) for i in range(count)]
    if typ == 'u16':
        f = struct.Struct(f'{e}{n}H')
        return [list(f.unpack_from(raw, i * stride + off)) for i in range(count)]
    if typ in ('u8', 'u8n'):
        scale = 255.0 if typ == 'u8n' else 1
        return [[c / scale if scale != 1 else c for c in raw[i * stride + off:i * stride + off + n]]
                for i in range(count)]
    if typ == 's10n':
        return [_s10n(struct.unpack_from(e + 'I', raw, i * stride + off)[0]) for i in range(count)]
    raise ValueError(f'unknown vertex format {n}{typ}')


def names(d):
    e = endian(d)
    for type_, off, _, _ in _sections(d):
        if type_ == NAMES:
            count = struct.unpack(e + 'I', d[off + 4:off + 8])[0]
            p, out = off + 16, []
            for _ in range(count):
                length = struct.unpack(e + 'I', d[p + 4:p + 8])[0]
                out.append(d[p + 8:p + 8 + length].split(b'\0')[0].decode('ascii', 'replace'))
                p += 8 + length
            return out
    return []


def meshes(d):
    """[{'name', 'attrs': {'p0': [[x, y, z, ...]], 'n0', 't0', ...}, 'indices': [...]}] of an RX3b/RX3l file.
    FIFA 14 heads have 8 bone influences (i0/w0 + i1/w1, u16 indices): read like the rest."""
    e = endian(d)
    secs = _sections(d)
    decls = [_decl(d[o:o + s]) for t, o, s, _ in secs if t == DECL]
    vbs = [(o, s) for t, o, s, _ in secs if t == VERTICES]
    ibs = [o for t, o, _, _ in secs if t == INDICES]
    mesh_names = [n for n in names(d) if n.endswith('.FxRenderableSimple')]
    out = []
    for i, (decl, (vo, vs), io) in enumerate(zip(decls, vbs, ibs)):
        _, count, stride, _ = struct.unpack(e + 'IIII', d[vo:vo + 16])
        raw = d[vo + 16:vo + vs]
        attrs = {name: _read(raw, count, stride, off, n, typ, e) for name, off, n, typ in decl}
        n_idx, idx_size = struct.unpack(e + 'I', d[io + 4:io + 8])[0], d[io + 8]
        fmt = e + ('%dH' % n_idx if idx_size == 2 else '%dI' % n_idx)
        indices = list(struct.unpack_from(fmt, d, io + 16))
        out.append({'name': mesh_names[i] if i < len(mesh_names) else f'mesh{i}', 'attrs': attrs,
                    'indices': indices})
    return out
