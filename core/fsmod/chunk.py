"""'chunklzx' / 'chunkzip' containers used by entries of the game's .big archives.

Layout: 'chunkXXX' | u32 2 | u32 total size | u32 chunk size | u32 chunk count | 4 x u32 | chunks, each one
at an offset = 8 mod 16: u32 zsize, u32 flag (3 = LZX, 1 = raw deflate, 4 = stored), data.
LZX = XMemCompress framing ('FF uuuu cccc' or 'cccc' blocks), window 2^17, decoded by bin/lzxdec.exe
(libmspack lzxd.c, LGPL 2.1; source and build command in app/core/lzx/).
"""
import os
import struct
import subprocess
import tempfile
import zlib

LZXDEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'lzxdec.exe')


def _xmem_frames(data):
    out, p = bytearray(), 0
    while p < len(data):
        if data[p] == 0xFF:
            _, c = struct.unpack('>HH', data[p + 1:p + 5])
            p += 5
        else:
            c = struct.unpack('>H', data[p:p + 2])[0]
            p += 2
        if c == 0:
            break
        out += data[p:p + c]
        p += c
    return bytes(out)


def _lzx(data, outlen, window_bits=17):
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, 'in'), os.path.join(d, 'out')
        with open(src, 'wb') as f:
            f.write(_xmem_frames(data))
        r = subprocess.run([LZXDEC, src, dst, str(window_bits), str(outlen)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError('lzxdec: ' + r.stderr.strip())
        with open(dst, 'rb') as f:
            return f.read()


def decode(b: bytes) -> bytes:
    """Decompresses a chunk container; returns the input unchanged when it is not one."""
    tag = b[:8]
    if not tag.startswith(b'chunk'):
        return b
    _, total, chunk_size, n = struct.unpack('>IIII', b[8:24])
    p, out = 0x28, bytearray()
    for _ in range(n):
        p += (8 - p % 16) % 16
        zsize, flag = struct.unpack('>II', b[p:p + 8])
        p += 8
        block = b[p:p + zsize]
        p += zsize
        want = min(chunk_size, total - len(out))
        if flag == 3:
            out += _lzx(block, want)
        elif flag == 1:
            out += zlib.decompress(block, -15)
        elif flag == 4:
            out += block
        else:
            raise ValueError(f'unknown chunk flag {flag} ({tag})')
    assert len(out) == total, (len(out), total)
    return bytes(out)


def chunkzip(raw: bytes, chunk_size=0x40000) -> bytes:
    """Multi-chunk 'chunkzip' (deflate level 9)."""
    parts = [raw[i:i + chunk_size] for i in range(0, len(raw), chunk_size)]
    out = bytearray(b'chunkzip' + struct.pack('>IIIII', 2, len(raw), chunk_size, len(parts), 0x10) + bytes(12))
    for part in parts:
        out += b'\0' * ((8 - len(out) % 16) % 16)
        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        z = co.compress(part) + co.flush()
        out += struct.pack('>II', len(z), 1) + z
    return bytes(out)


def unchunk_single(c: bytes) -> bytes:
    """Payload of a single-chunk 'chunkzip' (UI images such as crests and player photos)."""
    assert c[:8] == b'chunkzip', c[:8]
    full = struct.unpack('>I', c[12:16])[0]
    zsize, flag = struct.unpack('>II', c[0x28:0x30])
    data = c[0x30:0x30 + zsize]
    raw = zlib.decompress(data, -15) if flag == 1 else data
    assert len(raw) == full, (len(raw), full)
    return raw


def rechunk_single(template: bytes, raw: bytes) -> bytes:
    """Single-chunk 'chunkzip' reusing the 0x28-byte header of template (deflate level 9, memLevel 9)."""
    co = zlib.compressobj(9, zlib.DEFLATED, -15, 9)
    z = co.compress(raw) + co.flush()
    hdr = bytearray(template[:0x28])
    struct.pack_into('>I', hdr, 12, len(raw))
    return bytes(hdr) + struct.pack('>II', len(z), 1) + z
