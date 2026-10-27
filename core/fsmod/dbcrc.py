"""Check / recompute every CRC of a T3DB database (Xbox layout).

The game validates these when loading the database; a wrong one makes it crash with
"Unhandled guest access violation: read of guest 0x00000000".

Scheme (verified on 131/131 tables of the original database):
  - database header: crc(db[0x00:0x14]) stored at db[0x14:0x18] (covers the total size at 0x08)
  - catalog:         crc(db[0x18 : 0x18 + 8*N]) stored right after the catalog
  - each table:      crc(table[0x00:0x20]) at table[0x20:0x24] (header)
                     crc(table[0x24:end-4]) in the table's last 4 bytes (data)
"""
import struct

from .crc import crc32_mpeg2


def layout(db):
    if db[:2] != b'DB':
        raise ValueError('not a T3DB database (missing DB signature)')
    if db[4] != 1:
        raise ValueError('database is in PC (little-endian) layout; Xbox layout expected')
    n = struct.unpack('>I', db[16:20])[0]
    catalog_end = 0x18 + 8 * n
    base = catalog_end + 4
    offs = sorted(struct.unpack('>I', db[0x1C + 8 * i:0x20 + 8 * i])[0] for i in range(n))
    tables = [(base + o, base + offs[i + 1] if i + 1 < n else len(db)) for i, o in enumerate(offs)]
    return catalog_end, tables


def check(db):
    """List of descriptions of the CRCs that do not match (empty = all good)."""
    catalog_end, tables = layout(db)
    bad = []
    if crc32_mpeg2(db[:0x14]) != struct.unpack('>I', db[0x14:0x18])[0]:
        bad.append('database header (0x14)')
    if crc32_mpeg2(db[0x18:catalog_end]) != struct.unpack('>I', db[catalog_end:catalog_end + 4])[0]:
        bad.append('catalog')
    for start, end in tables:
        if crc32_mpeg2(db[start:start + 0x20]) != struct.unpack('>I', db[start + 0x20:start + 0x24])[0]:
            bad.append(f'table header 0x{start:X}')
        if crc32_mpeg2(db[start + 0x24:end - 4]) != struct.unpack('>I', db[end - 4:end])[0]:
            bad.append(f'table data 0x{start:X}')
    return bad


def fix(db):
    db = bytearray(db)
    catalog_end, tables = layout(db)
    struct.pack_into('>I', db, 8, len(db))
    struct.pack_into('>I', db, 0x14, crc32_mpeg2(db[:0x14]))
    for start, end in tables:
        struct.pack_into('>I', db, start + 0x20, crc32_mpeg2(db[start:start + 0x20]))
        struct.pack_into('>I', db, end - 4, crc32_mpeg2(db[start + 0x24:end - 4]))
    struct.pack_into('>I', db, catalog_end, crc32_mpeg2(db[0x18:catalog_end]))
    return bytes(db)
