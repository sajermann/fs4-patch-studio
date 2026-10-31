"""Editing the game's own leagues in place (League.original_id, fsmod.original_league), and teams without a league."""
import io
import os

import pytest
from PIL import Image

from fsmod import builder, leaguelogo, locale, model, original_league, original_team, t3db, validation
from fsmod.catalog import Catalog

PREMIER, ENGLAND = 13, 14
REST_OF_WORLD = 76  # hidden by the game's selector: not editable
BARCELONA = 241


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


def load(game, catalog, assets, leagueid=PREMIER, uid='lg_premier'):
    return original_league.load(game, catalog, leagueid, uid, assets[1])


def png(color, size=(300, 300)):
    buf = io.BytesIO()
    Image.new('RGBA', size, color).save(buf, format='PNG')
    return buf.getvalue()


def league_row(db, leagueid):
    t = db.by_name('leagues')
    return next(r for r in t.records if t.value(r, t.field('leagueid')) == leagueid)


def value(db, table, row, name):
    t = db.by_name(table)
    return t.value(row, t.field(name))


def test_load_fills_the_league_with_what_the_game_has(game, catalog, assets):
    lg = load(game, catalog, assets)
    assert lg.original_id == PREMIER and lg.key == PREMIER and lg.league_id is None
    assert (lg.name, lg.short_name, lg.sort_order) == ('Barclays Premier League', 'Barclays PL', 1)
    with Image.open(os.path.join(assets[0], lg.image)) as im:
        assert im.size == leaguelogo.ASSETS['flag_small'][4]
    with Image.open(os.path.join(assets[0], lg.wide_image)) as im:
        assert im.size == leaguelogo.ASSETS['flag_wide'][4]
    assert not original_league.changes(lg, assets[0]).any and original_league.untouched(lg, assets[0])
    with pytest.raises(KeyError):
        load(game, catalog, assets, REST_OF_WORLD)


def test_unchanged_original_league_changes_nothing(game, catalog, assets):
    project = model.Project(leagues=[load(game, catalog, assets)])
    result = builder.build(project, game, assets[0])
    plain = builder.build(model.Project(), game, assets[0])
    assert result.database == plain.database and result.entries.keys() == plain.entries.keys()
    assert not result.loose
    assert not validation.has_errors(validation.validate(project, catalog, assets[0]))


def test_edited_original_league_keeps_its_id_and_country(game, catalog, assets):
    folder, save_image = assets
    lg = load(game, catalog, assets)
    lg.name, lg.short_name, lg.sort_order = 'Premier Teste', 'PL Teste', 12
    lg.image = save_image('new-logo.png', png((90, 40, 130, 255)))
    project = model.Project(leagues=[lg])
    assert not validation.has_errors(validation.validate(project, catalog, folder))
    result = builder.build(project, game, folder)

    db = t3db.Database(result.database, game.meta)
    row = league_row(db, PREMIER)
    assert value(db, 'leagues', row, 'defaultsortorder') == 12 and value(db, 'leagues', row, 'countryid') == ENGLAND
    texts = locale.texts(result.entries['locale_ptbr.big', 'data/loc/eng_us.db'])
    assert texts[f'LeagueName_{PREMIER}'] == 'Premier Teste' and texts[f'LeagueName_Abbr15_{PREMIER}'] == 'PL Teste'
    # only the changed (square) flag of the league's country, in place inside data1
    small, wide = (leaguelogo.asset_name(a, ENGLAND) for a in ('flag_small', 'flag_wide'))
    assert ('data1.big', small) in result.entries and ('data1.big', wide) not in result.entries
    assert not result.loose
    shown = leaguelogo.read_image(result.entries['data1.big', small])[0].convert('RGBA')
    assert shown.getpixel((shown.width // 2, shown.height // 2)) == (90, 40, 130, 255)


def test_validation_of_original_leagues(game, catalog, assets):
    lg = load(game, catalog, assets)
    project = model.Project(leagues=[lg, lg.model_copy(update={'uid': 'lg_twin'})])
    codes = {i.code for i in validation.validate(project, catalog, assets[0])}
    assert 'original_league_edited_twice' in codes and 'league_image_missing' not in codes
    project.leagues = [lg.model_copy(update={'original_id': REST_OF_WORLD})]
    assert 'original_league_not_found' in {i.code for i in validation.validate(project, catalog, assets[0])}


def test_original_team_without_a_league_is_hidden_in_the_game(game, catalog, assets):
    tm = original_team.load(game, catalog, BARCELONA, 'tm_barca', assets[1])
    tm.leagues = []
    project = model.Project(teams=[tm])
    issues = validation.validate(project, catalog, assets[0])
    assert ('team_without_league', 'tm_barca') in {(i.code, i.entity) for i in issues}
    assert not validation.has_errors(issues)
    db = t3db.Database(builder.build(project, game, assets[0]).database, game.meta)
    t = db.by_name('leagueteamlinks')
    links = [r for r in t.records if t.value(r, t.field('teamid')) == BARCELONA]
    assert [t.value(r, t.field('leagueid')) for r in links] == [builder.HIDDEN_TEAMS_LEAGUE]


def test_new_team_without_a_league_is_left_out(game, catalog, assets):
    team = model.Team(uid='tm_new', name='Sem Liga', leagues=[], primary_color=(0, 0, 0),
                      secondary_color=(255, 255, 255))
    player = model.Player(uid='jg_new', first_name='A', last_name='B', teams=[model.TeamLink(team='tm_new')])
    project = model.Project(teams=[team], players=[player])
    assert project.visible().teams == [] and project.visible().players == []
    issues = validation.validate(project, catalog, assets[0])
    assert [(i.code, i.entity) for i in issues] == [('team_without_league', 'tm_new')]


def leagues_of(db, teamid):
    t = db.by_name('leagueteamlinks')
    rows = [r for r in t.records if t.value(r, t.field('teamid')) == teamid]
    keys = [t.value(r, t.field('artificialkey')) for r in rows]
    assert len(set(keys)) == len(keys)
    return sorted(t.value(r, t.field('leagueid')) for r in rows)


def test_a_team_plays_in_several_leagues(game, catalog, assets):
    folder = assets[0]
    tm = original_team.load(game, catalog, BARCELONA, 'tm_barca', assets[1])
    tm.leagues = [53, 39, PREMIER]  # stays in Liga BBVA, joins the MLS and the Premier League (test LT1)
    project = model.Project(teams=[tm])
    assert not validation.has_errors(validation.validate(project, catalog, folder))
    assert original_league.changed_teams(project, catalog) == [PREMIER, 39]
    db = t3db.Database(builder.build(project, game, folder).database, game.meta)
    assert leagues_of(db, BARCELONA) == [PREMIER, 39, 53]
    tm.leagues = [39]  # leaves Liga BBVA: that league changed too
    assert original_league.changed_teams(project, catalog) == [39, 53]
    tm.leagues = [53]
    assert original_league.changed_teams(project, catalog) == []
    tm.leagues = [53, 53]
    assert 'league_twice' in {i.code for i in validation.validate(project, catalog, folder)}


def test_old_projects_with_one_league_per_team_still_load():
    team = model.Team.model_validate({'uid': 't', 'name': 'T', 'league': 39, 'primary_color': [0, 0, 0],
                                      'secondary_color': [0, 0, 0]})
    assert team.leagues == [39]
    none = model.Team.model_validate({'uid': 't', 'name': 'T', 'league': None, 'primary_color': [0, 0, 0],
                                      'secondary_color': [0, 0, 0]})
    assert none.leagues == []


def test_version_2_projects_are_converted_and_saved_as_the_current_version():
    old = {'version': 2, 'leagues': [{'uid': 'lg_1', 'name': 'L', 'country': 14}],
           'teams': [{'uid': 'tm_1', 'name': 'T', 'league': 'lg_1', 'primary_color': [0, 0, 0],
                      'secondary_color': [0, 0, 0]}],
           'players': [{'uid': 'jg_1', 'first_name': 'A', 'last_name': 'B', 'team': 'tm_1', 'number': 9}]}
    saved = model.load(old).model_dump(mode='json')
    assert saved['version'] == model.CONTRACT_VERSION == 3
    assert saved['teams'][0]['leagues'] == ['lg_1']
    assert saved['players'][0]['teams'] == [{'team': 'tm_1', 'number': 9, 'position': None}]
    with pytest.raises(ValueError):  # a file from a newer app is refused, never read in part
        model.load({'version': model.CONTRACT_VERSION + 1})
