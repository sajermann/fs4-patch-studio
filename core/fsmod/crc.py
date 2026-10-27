"""CRC-32/MPEG-2 (poly 0x04C11DB7, not reflected, init 0xFFFFFFFF, no final xor), used by every T3DB CRC."""

_TABLE = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _TABLE.append(_c)


def crc32_mpeg2(data, crc=0xFFFFFFFF):
    for b in data:
        crc = _TABLE[((crc >> 24) ^ b) & 0xFF] ^ ((crc << 8) & 0xFFFFFFFF)
    return crc
