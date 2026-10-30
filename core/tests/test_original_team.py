"""Editing the game's own teams in place (Team.original_id, fsmod.original_team)."""
import io
import os

import pytest
from PIL import Image

from fsmod import builder, chunk, crest, kit, locale, model, original_team, t3db, validation
from fsmod.catalog import Catalog

BARCELONA, REAL_MADRID = 241, 243
MLS, SPAIN = 39, 53


@pytest.fixture(scope='module')
def catalog(game):
    return Catalog(game)


@pytest.fixture
def assets(tmp_path):
    os.makedirs(tmp_path / 'images')

    def save_image(name, data):
        path = f'images/{name}'
        (tmp_path / path).write_bytes(data)
        return path
    return str(tmp_path), save_image


def load(game, catalog, assets, teamid=BARCELONA, uid='tm_barca'):
    folder, save_image = assets
    return original_team.load(game, catalog, teamid, uid, save_image)


def rows_of(db, table, key, value):
    t = db.by_name(table)
    return [r for r in t.records if t.value(r, t.field(key)) == value]


def value(db, table, row, name):
    t = db.by_name(table)
    return t.value(row, t.field(name))


def test_load_fills_the_team_with_what_the_game_has(game, catalog, assets):
    tm = load(game, catalog, assets)
    assert tm.original_id == BARCELONA and tm.team_id is None
    assert tm.leagues == [SPAIN] and tm.abbreviation == 'BAR'
    assert tm.crest and tm.use_real_kits and set(tm.real_kits) == {'home', 'away', 'goalkeeper'}
    home = tm.real_kits['home']
    with Image.open(os.path.join(assets[0], home.jersey)) as im:
        assert im.size == (1024, 1024)
    with Image.open(os.path.join(assets[0], home.shorts)) as im:
        assert im.size == (1024, 512)
    assert set(tm.street_kits) == {'home', 'away'} and tm.street_kits['home'].top is not None
    assert not original_team.changes(tm, assets[0]).any


def test_unchanged_original_team_changes_nothing(game, catalog, assets):
    project = model.Project(teams=[load(game, catalog, assets)])
    result = builder.build(project, game, assets[0])
    plain = builder.build(model.Project(), game, assets[0])
    assert result.database == plain.database
    assert not result.loose
    assert not any(str(BARCELONA) in name for _, name in result.entries)
    assert not validation.has_errors(validation.validate(project, catalog, assets[0]))


def test_edited_original_team_keeps_its_id_and_changes_only_what_changed(game, catalog, assets):
    folder, save_image = assets
    tm = load(game, catalog, assets)
    tm.name, tm.abbreviation = 'Palmeiras', 'PAL'
    tm.primary_color = (0, 100, 0)
    tm.leagues = [MLS]
    buf = io.BytesIO()
    Image.new('RGBA', (300, 300), (0, 128, 0, 255)).save(buf, format='PNG')
    tm.crest = save_image('new-crest.png', buf.getvalue())
    tm.street_kits['away'].top = model.StreetPart(style=24, pattern=3, colors=[(1, 2, 3), (4, 5, 6), (7, 8, 9)])
    project = model.Project(teams=[tm])
    assert not validation.has_errors(validation.validate(project, catalog, folder))
    result = builder.build(project, game, folder)

    db = t3db.Database(result.database, game.meta)
    original = t3db.Database(game.original_db(), game.meta)
    team = rows_of(db, 'teams', 'teamid', BARCELONA)
    assert len(team) == 1 and len(rows_of(db, 'teams', 'teamid', BARCELONA)) == 1
    assert value(db, 'teams', team[0], 'teamname') == 'Palmeiras'
    assert [value(db, 'teams', team[0], f'teamcolor1{c}') for c in 'rgb'] == [0, 100, 0]
    before = rows_of(original, 'teams', 'teamid', BARCELONA)[0]
    for f in ('teamcolor2r', 'captainid', 'assetid'):
        assert value(db, 'teams', team[0], f) == value(original, 'teams', before, f)
    assert value(db, 'leagueteamlinks', rows_of(db, 'leagueteamlinks', 'teamid', BARCELONA)[0], 'leagueid') == MLS

    kits = {value(db, 'teamkits', r, 'teamkittypetechid'): r for r in rows_of(db, 'teamkits', 'teamtechid', BARCELONA)}
    old_kits = {value(original, 'teamkits', r, 'teamkittypetechid'): r
                for r in rows_of(original, 'teamkits', 'teamtechid', BARCELONA)}
    assert [value(db, 'teamkits', kits[1], f'top_geo_type_{n}') for n in range(1, 6)] == [24] * 5
    assert kits[0] == old_kits[0]  # home street kit untouched

    texts = locale.texts(result.entries['locale.big', 'data/loc/eng_us.db'])
    assert texts[f'TeamName_{BARCELONA}'] == 'Palmeiras' and texts[f'TeamName_Abbr3_{BARCELONA}'] == 'PAL'
    assert texts[f'TeamName_Abbr15_{BARCELONA}'] == locale.texts(game.locale()[1])[f'TeamName_Abbr15_{BARCELONA}']

    # files of the game's own teamid go inside their archives; kits keep their jersey (crest decal replaced)
    names = {name: short for short, name in result.entries}
    for label, _ in crest.UI_SIZES:
        assert names[crest.ui_crest_name(label, BARCELONA)] == 'data1.big'
    assert names[crest.scene_crest_name(BARCELONA)] == 'data3.big'
    for n in (0, 1, 2):
        assert names[kit.kit_name(BARCELONA, n)] == 'data3.big'
        assert kit.thumbnail_name(BARCELONA, n) not in names
    edited = chunk.decode(result.entries['data3.big', kit.kit_name(BARCELONA, 0)])
    game_kit = chunk.decode(game.read_entry(kit.kit_name(BARCELONA, 0))[2])
    from fsmod import rx3tex
    jersey = rx3tex.by_name(game_kit, 'jersey_cm')
    assert edited[jersey['off']:jersey['off'] + jersey['size']] == game_kit[jersey['off']:jersey['off'] + jersey['size']]
    assert not result.loose


def test_validation_of_original_teams(game, catalog, assets):
    tm = load(game, catalog, assets)
    twin = tm.model_copy(update={'uid': 'tm_twin'})
    project = model.Project(teams=[tm, twin])
    codes = {i.code for i in validation.validate(project, catalog, assets[0])}
    assert 'original_team_edited_twice' in codes and 'roster_empty' not in codes
    project.teams = [tm.model_copy(update={'original_id': 999999})]
    assert 'original_team_not_found' in {i.code for i in validation.validate(project, catalog, assets[0])}


def test_moved_original_team_counts_in_its_new_league(game, catalog, assets):
    tm = load(game, catalog, assets, REAL_MADRID, 'tm_real')
    tm.leagues = [MLS]
    mls = [t['id'] for t in catalog.teams if t['league'] == MLS]
    project = model.Project(teams=[tm])
    copies = [model.Team(uid=f'tm_{k}', name=f'T{k}', leagues=[MLS], primary_color=(0, 0, 0),
                         secondary_color=(0, 0, 0)) for k in range(builder.MAX_LEAGUE_TEAMS - len(mls) - 1)]
    project.teams += copies

    def too_many():
        return {i.params['count'] for i in validation.validate(project, catalog, assets[0])
                if i.code == 'league_too_many_teams'}
    assert too_many() == set()  # MLS + new teams + Real Madrid = the limit
    project.teams.append(model.Team(uid='tm_extra', name='X', leagues=[MLS], primary_color=(0, 0, 0),
                                    secondary_color=(0, 0, 0)))
    assert too_many() == {builder.MAX_LEAGUE_TEAMS + 1}


def test_original_team_captain_and_takers(game, catalog, assets):
    tm = load(game, catalog, assets)
    game_team = next(t for t in catalog.teams if t['id'] == BARCELONA)
    assert tm.captain == game_team['captain'] and tm.takers == game_team['takers']
    messi, xavi = 158023, 10535
    tm.captain = messi
    tm.takers['left_corner'] = messi
    result = builder.build(model.Project(teams=[tm]), game, assets[0])
    db = t3db.Database(result.database, game.meta)
    row = rows_of(db, 'teams', 'teamid', BARCELONA)[0]
    assert value(db, 'teams', row, 'captainid') == messi
    assert value(db, 'teams', row, 'leftcornerkicktakerid') == messi
    assert value(db, 'teams', row, 'rightcornerkicktakerid') == xavi  # untouched role keeps the game's
    tm.takers['penalty'] = 1  # not a Barcelona player
    codes = {(i.code, i.field) for i in validation.validate(model.Project(teams=[tm]), catalog, assets[0])}
    assert ('taker_not_in_roster', 'takers.penalty') in codes


def test_original_team_lineup(game, catalog, assets):
    """A lineup of an original team: fs4lineup rows with the game's playerids (a field player in goal works)."""
    tm = load(game, catalog, assets)
    messi, xavi = 158023, 10535
    tm.lineups = [model.Lineup(players=5, goalkeeper=True, tactic=1, starters=[messi, xavi])]
    project = model.Project(teams=[tm])
    issues = validation.validate(project, catalog, assets[0])
    assert 'lineup_goalkeeper_not_gk' in {i.code for i in issues} and not validation.has_errors(issues)
    db = t3db.Database(builder.build(project, game, assets[0]).database, game.meta)
    rows = rows_of(db, 'fs4lineup', 'teamid', BARCELONA)
    assert len(rows) == 2  # both sides
    squad = {p['id'] for p in catalog.players if BARCELONA in p['teams']}
    slots = [value(db, 'fs4lineup', rows[0], f'position{k}') for k in range(builder.LINEUP_SLOTS)]
    assert slots[:2] == [messi, xavi] and set(slots) == squad
    tm.lineups[0].starters = [1]
    assert 'lineup_player_not_in_roster' in {i.code for i in validation.validate(project, catalog, assets[0])}


def test_shorts_number_comes_from_the_game_and_can_be_switched(game, catalog, assets):
    tm = load(game, catalog, assets)
    assert tm.real_kits['home'].shorts_number is True  # licensed teams show the number on the shorts
    assert not original_team.changes(tm, assets[0]).any
    tm.real_kits['home'].shorts_number = False
    assert original_team.changes(tm, assets[0]).real_kits['home'] == {'settings'}
    db = t3db.Database(builder.build(model.Project(teams=[tm]), game, assets[0]).database, game.meta)
    kits = {value(db, 'teamkits', r, 'teamkittypetechid'): r for r in rows_of(db, 'teamkits', 'teamtechid', BARCELONA)}
    assert value(db, 'teamkits', kits[0], 'shortsnumberplacementcode') == 0
    assert value(db, 'teamkits', kits[1], 'shortsnumberplacementcode') == 1
