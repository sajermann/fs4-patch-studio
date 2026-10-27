"""BIG4 archives (dataN.big) and their ViV4 hash indexes (dataN.bh).

  dataN.big (BIG4)
    0x00 'BIG4' | 0x04 u32 LE total size | 0x08 u32 BE entry count | 0x0C u32 BE end of the name table
    0x10 entries: u32 BE offset, u32 BE size, ASCII name + \\0   (data aligned to 0x40, no trailing padding)

  dataN.bh (ViV4)
    0x00 'ViV4' | 0x04 u32 LE size | 0x08 u32 BE entry count | 0x0C u32 BE size
    0x10 20-byte entries (same order as the .big):
         u32 BE offset | u32 BE size | u32 0 | u32 BE unknown (copied from the original) | u32 BE djb2(name)
"""
import struct

ALIGN = 0x40


def djb2(data: bytes) -> int:
    h = 5381
    for c in data:
        h = (h * 33 + c) & 0xFFFFFFFF
    return h


def read_toc(data: bytes):
    """[(name, offset, size)] of a BIG4 archive."""
    if data[:4] != b'BIG4':
        raise ValueError('not a BIG4 archive')
    n = struct.unpack('>I', data[8:12])[0]
    pos, out = 16, []
    for _ in range(n):
        off, size = struct.unpack('>II', data[pos:pos + 8])
        pos += 8
        end = data.index(b'\0', pos)
        out.append((data[pos:end].decode('ascii'), off, size))
        pos = end + 1
    return out


def read_toc_file(path):
    """Same as read_toc, reading only the archive header."""
    with open(path, 'rb') as f:
        head = f.read(16)
        hdr_len = struct.unpack('>I', head[12:16])[0]
        return read_toc(head + f.read(hdr_len - 16))


def read_toc_positions(path):
    """({name: (position of its offset/size pair in the header, offset, size)}, header length) of a BIG4 file."""
    with open(path, 'rb') as f:
        head = f.read(16)
        n, hdr_len = struct.unpack('>II', head[8:16])
        data = head + f.read(hdr_len - 16)
    pos, out = 16, {}
    for _ in range(n):
        off, size = struct.unpack('>II', data[pos:pos + 8])
        end = data.index(b'\0', pos + 8)
        out[data[pos + 8:end].decode('ascii')] = (pos, off, size)
        pos = end + 1
    return out, hdr_len


def read_bh_entries(data: bytes):
    """[(offset, size, unknown, hash)] of a ViV4 index."""
    if data[:4] != b'ViV4':
        raise ValueError('not a ViV4 index')
    n = struct.unpack('>I', data[8:12])[0]
    out = []
    for i in range(n):
        off, size, _, unknown, h = struct.unpack('>IIIII', data[16 + i * 20:36 + i * 20])
        out.append((off, size, unknown, h))
    return out


def bh_unknown_by_name(bh_data: bytes, names):
    """{name: unknown .bh field} pairing a .bh with the names of its .big (same order)."""
    return {name: e[2] for name, e in zip(names, read_bh_entries(bh_data))}


def build_patch(entries, ref_unknown=None):
    """entries: [(internal_name, bytes)]. Returns (big_bytes, bh_bytes)."""
    ref_unknown = ref_unknown or {}
    names = [n.encode('ascii') for n, _ in entries]
    hdr_len = 16 + sum(8 + len(n) + 1 for n in names)
    offsets, cur = [], (hdr_len + ALIGN - 1) // ALIGN * ALIGN
    for _, data in entries:
        offsets.append(cur)
        cur = (cur + len(data) + ALIGN - 1) // ALIGN * ALIGN
    total = offsets[-1] + len(entries[-1][1])  # no trailing padding, like the originals

    big = bytearray(total)
    big[0:4] = b'BIG4'
    struct.pack_into('<I', big, 4, total)
    struct.pack_into('>II', big, 8, len(entries), hdr_len)
    pos = 16
    for (_, data), nb, off in zip(entries, names, offsets):
        struct.pack_into('>II', big, pos, off, len(data))
        pos += 8
        big[pos:pos + len(nb)] = nb
        pos += len(nb) + 1
        big[off:off + len(data)] = data
    assert pos == hdr_len

    bh_len = 16 + 20 * len(entries)
    bh = bytearray(bh_len)
    bh[0:4] = b'ViV4'
    struct.pack_into('<I', bh, 4, bh_len)
    struct.pack_into('>II', bh, 8, len(entries), bh_len)
    for i, ((name, data), nb, off) in enumerate(zip(entries, names, offsets)):
        struct.pack_into('>IIIII', bh, 16 + i * 20, off, len(data), 0, ref_unknown.get(name, 0), djb2(nb))
    return bytes(big), bytes(bh)
