"""Game texts (team / league names and any other string) in eng_us.db from locale.big.

Table LanguageStrings: key, text and a hash of the key; rows are sorted by the hash (the game looks keys up by
it). The hash is a CRC-32 of the key with every byte | 0x20 , so new keys can be
created. The rebuilt eng_us.db may grow: the bigger entry moves to the end of locale.big (validated in game).
"""
import bisect
import itertools
import zlib

from . import t3db

STRINGS_TABLE = 'GJCv'  # LanguageStrings: key, text, hash
HASH_SEED = 0x48FACC87


class LocaleError(Exception):
    pass


def strings_table(db):
    return db.tables[STRINGS_TABLE]


def keys(data: bytes):
    return {r[0].decode() for r in strings_table(t3db.Database(data)).records}


def texts(data: bytes):
    """{key: text} of the whole locale."""
    return {r[0].decode(): (r[1] or b'').decode('utf-8', 'replace')
            for r in strings_table(t3db.Database(data)).records}


def charset(data: bytes):
    """Characters the strings of a locale can be encoded with (its Huffman tree; rows are not decoded)."""
    return set(t3db.Database.table_huffman(data, STRINGS_TABLE).codes)


def missing_chars(data: bytes, text: str):
    return strings_table(t3db.Database(data)).huff.missing_chars(text.encode('utf-8'))


def key_hash(key: bytes) -> int:
    """Hash of a key as the game computes it (matches 21,051 of the 21,077 original keys; the others have
    non-ASCII characters)."""
    data = bytes(c | 0x20 for c in key)
    return zlib.crc32(data, HASH_SEED ^ 0xFFFFFFFF) ^ 0xFFFFFFFF ^ HASH_SEED


def set_strings(changes, data: bytes) -> bytes:
    """Applies {key: text}: existing keys get the new text, missing keys become new rows (kept in hash order)."""
    db = t3db.Database(data)
    table = strings_table(db)
    rows = {r[0]: r for r in table.records}
    hashes = {r[2] for r in table.records}
    # running max of the hashes (the table is not fully sorted): a new key goes before the first row whose hash is
    # bigger, i.e. at the first index where the running max is bigger (bisect, instead of scanning 21k rows per key)
    running_max = list(itertools.accumulate((r[2] for r in table.records), max))
    for key, value in changes.items():
        k = key.encode()
        encoded = value.encode('utf-8')
        table.huff.encode(encoded)  # validates the characters
        if k in rows:
            rows[k][1] = encoded
            continue
        h = key_hash(k)
        if h in hashes:
            raise LocaleError(f'locale key {key}: hash 0x{h:08X} already used by another key')
        pos = bisect.bisect_right(running_max, h)
        row = [k, encoded, h]
        table.records.insert(pos, row)
        table.raw_records.insert(pos, bytes(table.rec_size))
        hashes.add(h)
        running_max.insert(pos, h)  # every row before pos is <= h, every one after already had a bigger max
        rows[k] = row
    return db.build()
