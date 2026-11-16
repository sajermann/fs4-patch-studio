import io
import struct

import pytest
from PIL import Image, ImageFont

from fsmod import builder, chunk, model, uifonts, validation
from fsmod.catalog import Catalog


def user_font(game):
    """A font that stands for the user's file: the game's courier font (outlines, metrics and names of its own)."""
    return uifonts.original(game, 'courier')


def project_with(slot, path):
    return model.load({'version': model.CONTRACT_VERSION,
                       'game_patches': {'ui_fonts': {slot: {'file': path, 'name': 'Mine'}}}})


def test_slots_are_the_files_the_menus_load(game):
    listed = chunk.decode(game.read_entry(uifonts.FONTS_DIR + 'fonts.txt')[2]).decode('utf-8-sig').lower().split()
    assert [uifonts.SLOTS[s] for s in uifonts.SLOTS] == [f for f in listed if f != 'arial.ttf']
    assert set(uifonts.SLOTS) == set(model.UiFontSlot.__args__)
    for slot in uifonts.SLOTS:
        uifonts.check(uifonts.original(game, slot))
        assert uifonts.missing_chars(uifonts.original(game, slot)) == ''


def test_convert_keeps_the_original_names_and_its_size(game):
    own, mine = uifonts.original(game, 'cn_bold'), user_font(game)
    out = uifonts.convert(own, mine)
    _, out_tables = uifonts.tables(out)
    _, own_tables = uifonts.tables(own)
    assert out_tables[b'name'] == own_tables[b'name']
    assert out_tables[b'glyf'] == uifonts.tables(mine)[1][b'glyf']
    converted, original = ImageFont.truetype(io.BytesIO(out), 100), ImageFont.truetype(io.BytesIO(own), 100)
    assert converted.getname() == original.getname()
    assert converted.getmetrics() == original.getmetrics()
    assert abs(converted.getbbox('H')[1] - original.getbbox('H')[1]) <= 1  # capitals start at the same height
    assert abs(converted.getbbox('H')[3] - original.getbbox('H')[3]) <= 1
    # a valid file: table checksums and the whole-file checksum
    assert uifonts._checksum(out) == 0xB1B0AFBA
    n = struct.unpack('>H', out[4:6])[0]
    for i in range(n):
        tag, check, offset, length = struct.unpack('>4sIII', out[12 + 16 * i:28 + 16 * i])
        if tag != b'head':
            assert uifonts._checksum(out[offset:offset + length]) == check


def test_convert_drops_tables_that_no_longer_match(game):
    own = uifonts.original(game, 'body')
    mine = uifonts.original(game, 'ea05_body')  # has hdmx, VDMX and LTSH
    assert {b'hdmx', b'VDMX', b'LTSH'} <= set(uifonts.tables(mine)[1])
    assert not {b'hdmx', b'VDMX', b'LTSH'} & set(uifonts.tables(uifonts.convert(own, mine))[1])


def test_check_refuses_what_the_game_cannot_use():
    with pytest.raises(uifonts.UiFontError) as e:
        uifonts.check(b'OTTO' + bytes(100))
    assert e.value.code == 'ui_font_not_truetype'
    with pytest.raises(uifonts.UiFontError) as e:
        uifonts.check(b'not a font at all')
    assert e.value.code == 'ui_font_unreadable'


def test_missing_chars(game, monkeypatch):
    monkeypatch.setattr(uifonts, 'REQUIRED_CHARS', 'Aãༀ')
    assert uifonts.missing_chars(user_font(game)) == 'ༀ'
    assert uifonts.missing_chars(b'junk') == 'Aãༀ'


def test_build_replaces_the_chosen_fonts_only(game, tmp_path):
    (tmp_path / 'fonts').mkdir()
    (tmp_path / 'fonts' / 'ui-font-cn_bold.ttf').write_bytes(user_font(game))
    result = builder.build(project_with('cn_bold', 'fonts/ui-font-cn_bold.ttf'), game, str(tmp_path))
    fonts = {k: v for k, v in result.entries.items() if k[1].startswith(uifonts.FONTS_DIR)}
    assert list(fonts) == [('data0.big', 'data/ui/fonts/fs4_cn_bold.ttf')]
    font = ImageFont.truetype(io.BytesIO(chunk.decode(fonts['data0.big', 'data/ui/fonts/fs4_cn_bold.ttf'])), 20)
    assert font.getname() == ('Univers LT Std', '67 Bold Condensed')
    # no file = the game's font
    empty = model.load({'version': model.CONTRACT_VERSION, 'game_patches': {'ui_fonts': {'cn_bold': {}}}})
    assert not any(k[1].startswith(uifonts.FONTS_DIR) for k in builder.build(empty, game, str(tmp_path)).entries)


def test_validation(game, tmp_path, monkeypatch):
    catalog = Catalog(game)

    def issues(project):
        return [(i.code, i.severity, i.field) for i in validation.validate(project, catalog, str(tmp_path))
                if i.field and i.field.startswith('game_patches')]
    where = 'game_patches.ui_fonts.header'
    assert issues(project_with('header', 'fonts/gone.ttf')) == [('ui_font_file_not_found', 'error', where)]
    (tmp_path / 'fonts').mkdir()
    (tmp_path / 'fonts' / 'bad.ttf').write_bytes(b'OTTO' + bytes(64))
    assert issues(project_with('header', 'fonts/bad.ttf')) == [('ui_font_not_truetype', 'error', where)]
    (tmp_path / 'fonts' / 'good.ttf').write_bytes(user_font(game))
    assert issues(project_with('header', 'fonts/good.ttf')) == []
    monkeypatch.setattr(uifonts, 'REQUIRED_CHARS', 'Aༀ')
    assert issues(project_with('header', 'fonts/good.ttf')) == [('ui_font_missing_chars', 'warning', where)]


def test_preview_draws_the_game_font_or_the_converted_one(game):
    plain = Image.open(io.BytesIO(uifonts.preview(game, 'cn_bold')))
    mine = Image.open(io.BytesIO(uifonts.preview(game, 'cn_bold', user_font(game))))
    assert plain.size[1] == mine.size[1] and plain.getbbox() and mine.getbbox()
    assert plain.tobytes() != mine.tobytes()


def test_old_projects_open_without_fonts():
    assert model.load({'version': 15}).game_patches.ui_fonts == {}
    with pytest.raises(ValueError):
        model.load({'version': model.CONTRACT_VERSION, 'game_patches': {'ui_fonts': {'arial': {}}}})
