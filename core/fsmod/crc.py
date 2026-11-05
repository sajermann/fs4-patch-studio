"""CRC-32/MPEG-2 (poly 0x04C11DB7, not reflected, init 0xFFFFFFFF, no final xor), used by every T3DB CRC.

Same polynomial as zlib's CRC-32 with the bits mirrored, so zlib does the work: mirror the bits of every input byte
and of the register. Much faster than a Python byte loop on the database's big tables.
"""
import zlib

_MIRROR = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))


def _mirror32(value):
    return int.from_bytes(value.to_bytes(4, 'big').translate(_MIRROR)[::-1], 'big')


def crc32_mpeg2(data, crc=0xFFFFFFFF):
    register = zlib.crc32(data.translate(_MIRROR), _mirror32(crc) ^ 0xFFFFFFFF)
    return _mirror32(register ^ 0xFFFFFFFF)
