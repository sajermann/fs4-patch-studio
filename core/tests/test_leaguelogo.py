import os
import struct

import pytest
from PIL import Image

from conftest import FIXTURES
from fsmod import builder, chunk, leaguelogo, model
from test_builder import patched_entry

CREST = os.path.join(FIXTURES, 'palmeiras', 'escudo_palmeiras.png')
TEXTURES = {'flag_small': (128, 128), 'flag_wide': (256, 128)}


def template(game, asset):
    return game.read_entry(leaguelogo.asset_name(asset, leaguelogo.ASSETS[asset][3]))[2]


@pytest.mark.parametrize('asset', list(leaguelogo.ASSETS))
def test_templates_decode_and_their_archive_rewrites_identically(game, asset):
    raw = chunk.decode(template(game, asset))
    files, tail = leaguelogo.read_bigf(raw)
    assert tail[:4] == b'L286'
    end = struct.unpack('<I', raw[4:8])[0]
    assert leaguelogo.write_bigf(files, tail)[:end] == raw[:end]
    xpr = leaguelogo.refpack_decode(dict(files)[leaguelogo.IMAGE_ENTRY])
    assert leaguelogo.texture_info(xpr)[:3] == (leaguelogo.FMT_DXT5, *TEXTURES[asset])
    img, size = leaguelogo.read_image(template(game, asset))
    assert size == leaguelogo.ASSETS[asset][4] and img.getchannel('A').getbbox()


def test_new_flags_are_4x_uncompressed_and_placed_like_the_originals(game):
    crest = Image.open(CREST)
    wide = Image.new('RGBA', (300, 100), (0, 150, 70, 255))
    files = leaguelogo.flag_files(game, 54, crest)
    assert set(files) == {leaguelogo.asset_name(a, 54) for a in leaguelogo.ASSETS}
    k = leaguelogo.SCALE
    for asset, (_, _, _, _, region, box, _) in leaguelogo.ASSETS.items():
        entry = files[leaguelogo.asset_name(asset, 54)]
        names, tail = leaguelogo.read_bigf(chunk.decode(entry))
        assert [n for n, _ in names] == ['0', '3', 'sg1', '2', 'sg2', '1'] and tail[:4] == b'L286'
        xpr = dict(names)[leaguelogo.IMAGE_ENTRY]
        tw, th = TEXTURES[asset]
        assert leaguelogo.texture_info(xpr)[:3] == (leaguelogo.FMT_RGBA, tw * k, th * k)
        assert struct.unpack('>II', dict(names)['0'][0x40:0x48]) == (region[0] * k, region[1] * k)
        img, size = leaguelogo.read_image(entry)
        assert size == (region[0] * k, region[1] * k)
        left, top, right, bottom = img.getchannel('A').point(lambda a: 255 if a > 128 else 0).getbbox()
        assert right - left <= box[0] * k + 2 and bottom - top <= box[1] * k + 2
        assert abs(top - (size[1] - bottom)) <= 3 and abs(left - (size[0] - right)) <= 3  # centered
    # separate wide image: 'contain' leaves the sides empty, 'cover' fills the whole area
    for fit, filled in (('contain', False), ('cover', True)):
        entry = leaguelogo.flag_files(game, 54, crest, wide, fit)[leaguelogo.asset_name('flag_wide', 54)]
        img, size = leaguelogo.read_image(entry)
        assert (img.getchannel('A').getbbox() == (0, 0, *size)) == filled
        assert img.getpixel((size[0] // 2, size[1] // 2))[:3] == (0, 150, 70)


def test_every_league_gets_an_image_country_of_its_own(game, tmp_path):
    """The selector shows the flag of the league's country: each new league takes a country no nation uses
    (217-255, validated in game 22/10) and its image goes as that country's flag, in loose files."""
    from fsmod import validation
    from fsmod.catalog import Catalog
    Image.open(CREST).save(tmp_path / 'logo.png')
    project = model.Project(leagues=[
        model.League(uid='lg_a', name='Liga A', image='logo.png'),
        model.League(uid='lg_b', name='Liga B', image='logo.png'),
        model.League(uid='lg_c', name='Liga C')])
    result = builder.build(project, game, str(tmp_path))
    assert set(result.loose) == {leaguelogo.asset_name(a, c) for a in leaguelogo.ASSETS for c in (217, 218)}
    assert not [name for (_, name) in result.entries if 'countryflags' in name]
    db = builder.Db(result.database, game.meta)
    leagues = db.table('leagues')
    countries = {db.get(leagues, r, 'leagueid'): db.get(leagues, r, 'countryid') for r in leagues.records}
    assert [countries[result.assigned_league_ids[lg.uid]] for lg in project.leagues] == [217, 218, 219]
    assert max(c for c in countries.values() if c < 217) <= 216
    catalog = Catalog(game)
    assert [(i.code, i.entity) for i in validation.validate(project, catalog, str(tmp_path))
            if i.code.startswith('league_image')] == [('league_image_missing', 'lg_c')]
    project.leagues += [model.League(uid=f'x{k}', name=f'X {k}') for k in range(37)]
    assert 'too_many_leagues' in [i.code for i in validation.validate(project, catalog, str(tmp_path))]
    with pytest.raises(builder.BuildError, match='at most 39'):
        builder.build(project, game, str(tmp_path))
    project.leagues = project.leagues[:2]
    result = builder.build(project, game, str(tmp_path))

    out = tmp_path / 'patch'
    builder.write_patch(result, game, str(out))
    for name, data in result.loose.items():
        assert (out / 'Game' / name).read_bytes() == data

    result.loose.clear()  # loose files of an earlier build are removed
    builder.write_patch(result, game, str(out))
    for name in leaguelogo.ASSETS:
        assert not (out / 'Game' / leaguelogo.asset_name(name, 217)).exists()
