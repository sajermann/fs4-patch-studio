import pytest

from fsmod import crc, dbcrc, t3db


def test_crc_matches_the_standard_check_value():
    assert crc.crc32_mpeg2(b'123456789') == 0x0376E6E7
    assert crc.crc32_mpeg2(b'') == 0xFFFFFFFF
    # continuing from a previous value is the same as one call over everything
    assert crc.crc32_mpeg2(b'6789', crc.crc32_mpeg2(b'12345')) == 0x0376E6E7


def test_bits_are_read_and_written_msb_first_without_touching_the_neighbours():
    buf = bytearray(b'\xFF\x00\xFF')
    assert t3db.get_bits(buf, 4, 8) == 0xF0
    assert t3db.get_bits(buf, 4, 0) == 0
    t3db.set_bits(buf, 6, 4, 0b0110)
    assert buf == bytearray([0b11111101, 0b10000000, 0xFF])
    t3db.set_bits(buf, 0, 4, 0b10011)  # only the low n bits of the value count
    assert buf[0] == 0b00111101
    with pytest.raises(IndexError):
        t3db.get_bits(buf, 20, 8)
    with pytest.raises(IndexError):
        t3db.set_bits(buf, 20, 8, 0)


def test_huffman_decode_stops_at_the_byte_of_the_last_character():
    # tree: 0 -> 'a', 10 -> 'b', 11 -> 'c'
    tree = bytes([0, ord('a'), 1, 0]) + bytes([0, ord('b'), 0, ord('c')])
    huffman = t3db.Huffman(tree)
    # bytes used = length prefix + bytes holding the bits; the extra padding byte EA's encoder adds does not count
    for text, used in ((b'', 1), (b'a', 2), (b'abc', 2), (b'aaaaaaaa', 2), (b'cccc', 2), (b'abcabcabcabc', 4)):
        encoded = huffman.encode(text)
        for tail in (b'', b'\xFF\xFF'):  # what comes after is the next string: never read as this one
            assert huffman.decode(b'\x00' + encoded + tail, 1) == (text, used)
    with pytest.raises(ValueError, match='without a Huffman code'):
        huffman.encode(b'abz')


def test_original_database_round_trip_is_byte_identical(game):
    original = game.original_db()
    assert t3db.Database(original, game.meta).build() == original


def test_locales_rebuild_with_their_own_string_layout(game):
    """locale.big (EA) rebuilds byte-identical; locale_ptbr.big (ReStreet) stores equal strings once and pads
    them to the exact byte, which t3db detects and repeats (its area only lacks 8 stray bytes of the original)."""
    from fsmod import locale
    from fsmod.game import LOCALE_PTBR_FILE
    _, eng = game.locale()
    db = t3db.Database(eng)
    table = locale.strings_table(db)
    assert not table.shared_strings and not table.huff.exact_padding
    assert db.build() == eng
    _, ptbr = game.locale(LOCALE_PTBR_FILE)
    db = t3db.Database(ptbr)
    table = locale.strings_table(db)
    assert table.shared_strings and table.huff.exact_padding
    rebuilt = db.build()
    assert len(ptbr) - 8 <= len(rebuilt) <= len(ptbr)
    assert locale.texts(rebuilt) == locale.texts(ptbr)
    assert locale.texts(locale.set_strings({}, ptbr)) == locale.texts(ptbr)


def test_original_database_crcs_are_valid(game):
    assert dbcrc.check(game.original_db()) == []


def test_fix_repairs_a_broken_header_crc(game):
    broken = bytearray(game.original_db())
    broken[0x14] ^= 0xFF
    assert dbcrc.check(bytes(broken)) == ['database header (0x14)']
    assert dbcrc.fix(bytes(broken)) == game.original_db()


def test_human_values_apply_rangelow(game):
    db = t3db.Database(game.original_db(), game.meta)
    players = db.by_name('players')
    pid = players.field('playerid')
    assert any(players.value(r, pid) == 106573 for r in players.records)


def test_database_extracted_from_data0_matches_the_original_backup(game):
    import os
    from conftest import REPO
    backup = os.path.join(REPO, 'pesquisa', 'bancos', 'fifa_street_db_original_backup.db')
    if not os.path.exists(backup):
        import pytest
        pytest.skip('original backup not available')
    with open(backup, 'rb') as f:
        assert game.original_db() == f.read()
