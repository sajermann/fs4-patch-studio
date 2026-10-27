"""Reader/writer for the T3DB v6 database used by FIFA Street (2012), Xbox 360 layout (big-endian).

Layout:
  0x18-byte header + catalog (8*N) + catalog CRC + tables.
  Table: 0x24-byte header | N field descriptors (16 bytes) | records | string area | padding | CRC.
  Records: bit-packed fields, MSB-first, position = descriptor bit_offset.
  Field types: 0 = fixed string (depth bits), 3 = integer (raw value; real value = raw + meta rangelow),
               4 = float32, 13/14 = string in the string area (field holds a u32 offset; 0xFFFFFFFF = empty;
               13 = 1-byte length prefix, 14 = 2-byte length prefix).
  Huffman string area: tree (4-byte nodes: two 2-byte children; (idx,0) = inner node, (0,char) = leaf)
  followed by the strings: [length in bytes][bits MSB-first, padded to a byte].
  Every CRC is CRC-32/MPEG-2 (see dbcrc.py).
"""
import re
import struct

from .crc import crc32_mpeg2


# ---------------------------------------------------------------- bits
def get_bits(buf, bitpos, n):
    v = 0
    for i in range(n):
        p = bitpos + i
        v = (v << 1) | ((buf[p >> 3] >> (7 - (p & 7))) & 1)
    return v


def set_bits(buf, bitpos, n, v):
    for i in range(n):
        p = bitpos + n - 1 - i
        if (v >> i) & 1:
            buf[p >> 3] |= 1 << (7 - (p & 7))
        else:
            buf[p >> 3] &= ~(1 << (7 - (p & 7))) & 0xFF


# ---------------------------------------------------------------- Huffman
class Huffman:
    def __init__(self, tree: bytes):
        self.tree = tree
        # EA's encoder always adds at least one padding bit; ReStreet's locale_ptbr.big pads to the exact byte
        self.exact_padding = False
        self.nodes = [(tree[4 * i:4 * i + 2], tree[4 * i + 2:4 * i + 4]) for i in range(len(tree) // 4)]
        self.codes = {}
        self._walk(0, '')

    def _walk(self, idx, prefix):
        for bit, e in (('0', self.nodes[idx][0]), ('1', self.nodes[idx][1])):
            if e[1] != 0 or e[0] == 0:
                self.codes[e[1]] = prefix + bit
            else:
                self._walk(e[0], prefix + bit)

    @staticmethod
    def tree_size(area: bytes):
        """Tree length in bytes = (highest referenced node index + 1) * 4."""
        seen, stack, highest = set(), [0], 0
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            highest = max(highest, i)
            for e in (area[4 * i:4 * i + 2], area[4 * i + 2:4 * i + 4]):
                if e[1] == 0 and e[0] != 0:
                    stack.append(e[0])
        return (highest + 1) * 4

    def decode(self, area, off, prefix_len=1):
        n = int.from_bytes(area[off:off + prefix_len], 'big')
        out = bytearray()
        bit, cur = (off + prefix_len) * 8, 0
        while len(out) < n:
            b = (area[bit >> 3] >> (7 - (bit & 7))) & 1
            bit += 1
            e = self.nodes[cur][b]
            if e[1] != 0 or e[0] == 0:
                out.append(e[1])
                cur = 0
            else:
                cur = e[0]
        return bytes(out), ((bit + 7) >> 3) - off

    def missing_chars(self, s: bytes):
        return sorted({chr(c) for c in s if c not in self.codes})

    def nbits(self, s: bytes):
        return sum(len(self.codes[c]) for c in s)

    def encoded_size(self, s: bytes, prefix_len=1):
        """Size of encode(s) without encoding it."""
        n = self.nbits(s)
        return prefix_len + ((n + 7) // 8 if self.exact_padding else n // 8 + 1)

    def encode(self, s: bytes, prefix_len=1):
        missing = self.missing_chars(s)
        if missing:
            raise ValueError(f'characters without a Huffman code in this table: {missing}')
        bits = ''.join(self.codes[c] for c in s)
        # EA's encoder uses nbits//8 + 1 bytes (at least one padding bit); exact_padding: (nbits + 7) // 8
        bits += '0' * (-len(bits) % 8 if self.exact_padding else 8 - len(bits) % 8)
        return len(s).to_bytes(prefix_len, 'big') + (int(bits, 2).to_bytes(len(bits) // 8, 'big') if bits else b'')


class PlainStrings:
    """Uncompressed string area: [length][bytes]."""
    tree = b''

    @staticmethod
    def decode(area, off, prefix_len=1):
        n = int.from_bytes(area[off:off + prefix_len], 'big')
        return bytes(area[off + prefix_len:off + prefix_len + n]), n + prefix_len

    @staticmethod
    def missing_chars(s: bytes):
        return []

    @staticmethod
    def encode(s: bytes, prefix_len=1):
        return len(s).to_bytes(prefix_len, 'big') + s

    @staticmethod
    def encoded_size(s: bytes, prefix_len=1):
        return prefix_len + len(s)


# ---------------------------------------------------------------- meta
def load_meta(path):
    with open(path, encoding='utf-8') as f:
        return parse_meta(f.read())


def parse_meta(txt):
    """{table_shortname: (table_name, {field_shortname: (name, type, depth, rangelow, rangehigh)})}"""
    out = {}
    for tm in re.finditer(r'<table name="([^"]+)" shortname="([^"]+)"[^>]*>(.*?)</table>', txt, re.S):
        fields = {}
        for fm in re.finditer(r'<field ([^>]*)/>', tm.group(3)):
            a = dict(re.findall(r'(\w+)="([^"]*)"', fm.group(1)))
            fields[a['shortname']] = (a['name'], a['type'], int(a['depth']),
                                      int(a.get('rangelow', 0)), int(a.get('rangehigh', 0)))
        out[tm.group(2)] = (tm.group(1), fields)
    return out


# ---------------------------------------------------------------- tables
class Field:
    __slots__ = ('type', 'bitoff', 'short', 'depth', 'name', 'rangelow', 'meta_type')

    def __init__(self, type_, bitoff, short, depth):
        self.type, self.bitoff, self.short, self.depth = type_, bitoff, short, depth
        self.name, self.rangelow, self.meta_type = short, 0, None


class Table:
    def __init__(self, short, raw: bytes, meta=None):
        self.short = short
        h = raw[:0x24]
        (self.flags, self.rec_size, self.rec_bits, strsz, nvalid, nrec, self.unk14,
         nfields) = struct.unpack('>IIIIHHIB', h[:0x19])
        self.hdr_rest = h[0x19:0x20]  # bytes 0x19..0x1f are preserved as-is
        self.name = short
        self.fields = []
        for k in range(nfields):
            t, bo, sn, dp = struct.unpack('>II4sI', raw[0x24 + 16 * k:0x34 + 16 * k])
            self.fields.append(Field(t, bo, sn.decode('latin1'), dp))
        if meta and short in meta:
            self.name, meta_fields = meta[short]
            for f in self.fields:
                if f.short in meta_fields:
                    f.name, f.meta_type, _, f.rangelow, _ = meta_fields[f.short]
        self.nvalid = nvalid
        p = 0x24 + 16 * nfields
        recs = raw[p:p + self.rec_size * nrec]
        p += self.rec_size * nrec
        area = raw[p:p + strsz]
        self.area_size = strsz  # original string area size (header)
        self.huff = None
        if any(f.type in (13, 14) for f in self.fields):
            # flag 0x40 = Huffman strings; without it = plain [length][bytes]
            self.huff = Huffman(area[:Huffman.tree_size(area)]) if self.flags & 0x40 else PlainStrings()
        self.records = []
        self.raw_records = []  # original bytes (keeps bits that are outside any field)
        self.nrec_orig = nrec
        seen_offsets = {}
        decoded = {}  # (offset, prefix length) -> (string, bytes used), reused by _detect_exact_padding
        self.shared_strings = False  # True when rows point to the same string (e.g. ReStreet's locale_ptbr.big)
        for r in range(nrec):
            rb = recs[r * self.rec_size:(r + 1) * self.rec_size]
            self.raw_records.append(rb)
            row = []
            for f in self.fields:
                if f.type in (13, 14):
                    off = get_bits(rb, f.bitoff, 32)
                    if off != 0xFFFFFFFF:
                        self.shared_strings |= seen_offsets.setdefault(off, (r, f.short)) != (r, f.short)
                    if off == 0xFFFFFFFF:
                        row.append(None)
                    else:
                        key = (off, 2 if f.type == 14 else 1)
                        if key not in decoded:
                            decoded[key] = self.huff.decode(area, *key)
                        row.append(decoded[key][0])
                elif f.type == 0:
                    row.append(rb[f.bitoff // 8:(f.bitoff + f.depth) // 8])
                else:
                    row.append(get_bits(rb, f.bitoff, 32 if f.type == 4 else f.depth))
            self.records.append(row)
        if isinstance(self.huff, Huffman):
            self.huff.exact_padding = self._detect_exact_padding(decoded)

    def _detect_exact_padding(self, decoded):
        """True when a string whose bits fill whole bytes is stored without the extra padding byte.
        decoded: {(offset, prefix length): (string, bytes used)} of every string of the table."""
        starts = sorted(decoded)
        for (off, prefix_len), (nxt, _) in zip(starts, starts[1:]):
            s, used = decoded[off, prefix_len]
            if self.huff.nbits(s) % 8 == 0 and nxt - off == used:
                return True
        return False

    def value(self, row, f):
        """Human value of field f in row (applies rangelow, decodes strings and floats)."""
        v = row[self.fields.index(f)]
        if f.type == 3:
            return v + f.rangelow
        if f.type == 4:
            return struct.unpack('>f', struct.pack('>I', v))[0]
        if f.type == 0:
            return v.split(b'\0')[0].decode('utf-8', 'replace')
        if f.type in (13, 14):
            return None if v is None else v.decode('utf-8', 'replace')
        return v

    def field(self, name):
        for f in self.fields:
            if f.name == name or f.short == name:
                return f
        raise KeyError(name)

    def build(self) -> bytes:
        nfields = len(self.fields)
        area = bytearray()
        offsets = []
        if self.huff:
            area += self.huff.tree
            written = {}  # (field type, text) -> offset, when equal strings are stored once
            for row in self.records:
                offs = []
                for f, v in zip(self.fields, row):
                    if f.type not in (13, 14):
                        continue
                    if v is None:
                        offs.append(0xFFFFFFFF)
                    elif self.shared_strings and (f.type, v) in written:
                        offs.append(written[f.type, v])
                    else:
                        offs.append(len(area))
                        written[f.type, v] = len(area)
                        area += self.huff.encode(v, 2 if f.type == 14 else 1)
                offsets.append(offs)
        recs = bytearray(self.rec_size * len(self.records))
        for r, raw_r in enumerate(self.raw_records[:len(self.records)]):
            recs[r * self.rec_size:(r + 1) * self.rec_size] = raw_r
        for r, row in enumerate(self.records):
            base = r * self.rec_size * 8
            si = 0
            for f, v in zip(self.fields, row):
                if f.type in (13, 14):
                    set_bits(recs, base + f.bitoff, 32, offsets[r][si])
                    si += 1
                elif f.type == 0:
                    o = r * self.rec_size + f.bitoff // 8
                    recs[o:o + len(v)] = v
                else:
                    set_bits(recs, base + f.bitoff, 32 if f.type == 4 else f.depth, v)
        n = len(self.records)
        hdr = struct.pack('>IIIIHHIB', self.flags, self.rec_size, self.rec_bits, len(area),
                          self.nvalid if n == self.nrec_orig else n, n, self.unk14, nfields) + self.hdr_rest
        hdr += struct.pack('>I', crc32_mpeg2(hdr))
        body = bytearray()
        for f in self.fields:
            body += struct.pack('>II4sI', f.type, f.bitoff, f.short.encode('latin1'), f.depth)
        body += recs + area
        # padding only for tables with a string area: total size (including the CRC) multiple of 8
        if area:
            body += b'\0' * (-(len(hdr) + len(body) + 4) % 8)
        return bytes(hdr + body) + struct.pack('>I', crc32_mpeg2(bytes(body)))


class Database:
    def __init__(self, data: bytes, meta=None):
        if data[:2] != b'DB' or data[4] != 1:
            raise ValueError('expected a T3DB database in Xbox (big-endian) layout')
        self.header = data[:0x18]
        n = struct.unpack('>I', data[16:20])[0]
        self.catalog = [(data[0x18 + 8 * i:0x1C + 8 * i].decode('latin1'),
                         struct.unpack('>I', data[0x1C + 8 * i:0x20 + 8 * i])[0]) for i in range(n)]
        base = 0x18 + 8 * n + 4
        order = sorted(range(n), key=lambda i: self.catalog[i][1])
        self.tables = {}
        self.order = [self.catalog[i][0] for i in order]  # physical order
        for k, i in enumerate(order):
            start = base + self.catalog[i][1]
            end = base + self.catalog[order[k + 1]][1] if k + 1 < n else len(data)
            self.tables[self.catalog[i][0]] = Table(self.catalog[i][0], data[start:end], meta)

    @staticmethod
    def table_huffman(data: bytes, short):
        """Huffman tree of one table, read without decoding its rows (fast; e.g. which characters it can store)."""
        n = struct.unpack('>I', data[16:20])[0]
        base = 0x18 + 8 * n + 4
        for i in range(n):
            if data[0x18 + 8 * i:0x1C + 8 * i].decode('latin1') == short:
                t = base + struct.unpack('>I', data[0x1C + 8 * i:0x20 + 8 * i])[0]
                _, rec_size, _, strsz, _, nrec, _, nfields = struct.unpack('>IIIIHHIB', data[t:t + 0x19])
                area = data[t + 0x24 + 16 * nfields + rec_size * nrec:][:strsz]
                return Huffman(area[:Huffman.tree_size(area)])
        raise KeyError(short)

    @classmethod
    def open(cls, db_path, meta_path=None):
        with open(db_path, 'rb') as f:
            return cls(f.read(), load_meta(meta_path) if meta_path else None)

    def by_name(self, name):
        for t in self.tables.values():
            if t.name == name or t.short == name:
                return t
        raise KeyError(name)

    def build(self) -> bytes:
        blobs, offs, cur = {}, {}, 0
        for sn in self.order:
            blobs[sn] = self.tables[sn].build()
            offs[sn] = cur
            cur += len(blobs[sn])
        cat = b''.join(sn.encode('latin1') + struct.pack('>I', offs[sn]) for sn, _ in self.catalog)
        out = bytearray(self.header) + cat + struct.pack('>I', crc32_mpeg2(cat))
        for sn in self.order:
            out += blobs[sn]
        struct.pack_into('>I', out, 8, len(out))
        # 0x14 = CRC of db[0:0x14], which includes the total size. Without it the game rejects any
        # database whose size differs from the original (found with Frida, 19/10).
        struct.pack_into('>I', out, 0x14, crc32_mpeg2(bytes(out[:0x14])))
        return bytes(out)
