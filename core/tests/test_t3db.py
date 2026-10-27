from fsmod import dbcrc, t3db


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
