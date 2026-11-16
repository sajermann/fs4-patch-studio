"""Conversion rules of FIFA patch packages (fsmod.fifapackage), with a small set of rules of their own."""
import io
import json
import zipfile

import pytest

from fsmod import fifapackage as fp

ASCII = set(range(0x20, 0x7F))
RULES = fp.Rules(player_name_bytes=ASCII, text_bytes=ASCII | {0xC3, 0xA9},  # é is \xc3\xa9
                 appearance={'headtypecode': [0, 10, 20], 'skintonecode': [2, 4]},
                 nations={34: ['Netherlands', 'Holland'], 7: ['Ivory Coast', 'Ivory Coast']})


def test_clean_text():
    assert fp.clean_text('Jürgen  Æsir', ASCII) == 'Jurgen AEsir'
    assert fp.clean_text('Café', RULES.text_bytes) == 'Café'  # kept when the game can show it
    assert fp.clean_text('“Quoted”', ASCII) == '"Quoted"'
    assert fp.clean_text('A very long team name', ASCII, 6) == 'A very'


def test_nearest_and_nations():
    assert fp.nearest(14, [0, 10, 20]) == 10 and fp.nearest(15, [0, 10, 20]) == 10  # a tie goes to the smaller
    assert fp.nearest(5, []) == 5
    assert RULES.nation('holland') == 34 and RULES.nation("Côte d'Ivoire") == 7 and RULES.nation('Nowhere') is None


def test_skills():
    s = fp.skills({'overall': 120, 'acceleration': 10, 'sprint_speed': 10, 'skill_moves': 4}, keeper=True)
    assert s['overall'] == 99 and s['TRI'] == 4 and s['SPE'] == fp.KEEPER_MIN_SPE
    assert fp.skills({}, keeper=False)['ATH'] == 50


def test_number_color():
    assert fp.number_color(3, None) == 3  # no ink known: the index
    assert fp.number_color(3, [0, 70, 180]) == 3  # the ink is the palette's blue
    assert fp.number_color(15, [0, 20, 82]) == 13  # a club font that ignores the palette: the closest color


def _zip(manifest):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('package.json', json.dumps(manifest))
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_manifest_checks():
    with pytest.raises(fp.PackageError) as e:
        fp.read_manifest(_zip({'format': 'other'}))
    assert e.value.code == 'invalid_package'
    with pytest.raises(fp.PackageError) as e:
        fp.read_manifest(_zip({'format': fp.FORMAT, 'format_version': fp.FORMAT_VERSION + 1}))
    assert e.value.code == 'package_too_new'
    with pytest.raises(fp.PackageError) as e:
        fp.convert(_zip({'format': fp.FORMAT, 'format_version': 1}), RULES, 'bad prefix')
    assert e.value.code == 'invalid_prefix'


def test_convert_minimal():
    items, files, _ = fp.convert(_zip({
        'format': fp.FORMAT, 'format_version': 1,
        'teams': [{'source_id': 5, 'names': {'database': 'Old Boys 1950-55'}, 'roster': [{'player_id': 6}],
                   'league_ids': [1]}],
        'players': [{'source_id': 6, 'names': {'common': 'Pelé'}, 'positions': [{'code': 0}],
                     'teams': [{'team_id': 5, 'jersey_number': 1, 'position': 29}],
                     'appearance': {'headtypecode': 14}, 'nationality_id': 1}],
        'nations': [{'source_id': 1, 'name': 'Holland'}],
    }), RULES, 'x-')
    team, = items['teams']
    assert team['short_name'] == 'Old Boys' and team['abbreviation'] == 'OLD' and team['leagues'] == []
    assert team['captain'] == 'x-p6' and team['use_real_kits'] is False and team['crest'] is None
    player, = items['players']
    assert player['first_name'] == player['last_name'] == player['display_name'] == 'Pele'
    assert player['teams'] == [{'team': 'x-t5', 'number': 1, 'position': 0}]  # a reserve link: his own position
    assert player['appearance'] == {'headtypecode': 10} and player['fields']['nationality'] == 34
    assert player['generic'] is True and files['players'] == {}
