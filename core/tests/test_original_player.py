"""Editing the game's own players in place (Player.original_id, fsmod.original_player) and players in several teams."""
import os

import pytest

from fsmod import builder, model, original_player, t3db, validation
from fsmod.catalog import Catalog
from test_builder import PALMEIRAS, load_palmeiras

MESSI, XAVI = 158023, 10535
BARCELONA, BRAZIL = 241, 1370


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


def entry(game, catalog, playerid, uid, save_image=None):
    """Original player entry; without save_image its photo is left out (the project folder is a fixture)."""
    pl = original_player.load(game, catalog, playerid, uid, save_image or (lambda name, data: None))
    if save_image is None:
        pl.photo = None
        pl.loaded.images.pop('photo', None)
    return pl


def rows_of(db, table, key, value):
    t = db.by_name(table)
    return [r for r in t.records if t.value(r, t.field(key)) == value]


def value(db, table, row, name):
    t = db.by_name(table)
    return t.value(row, t.field(name))


def links_of(db, playerid):
    return {value(db, 'teamplayerlinks', r, 'teamid'): (value(db, 'teamplayerlinks', r, 'jerseynumber'),
                                                         value(db, 'teamplayerlinks', r, 'position'))
            for r in rows_of(db, 'teamplayerlinks', 'playerid', playerid)}


def test_load_fills_the_player_with_what_the_game_has(game, catalog, assets):
    folder, save_image = assets
    pl = entry(game, catalog, MESSI, 'jg_messi', save_image)
    info = catalog.players_by_id[MESSI]
    assert pl.original_id == MESSI and pl.ref == MESSI and pl.player_id is None
    assert pl.shown_name == info['display_name'] and not pl.generic
    assert [lk.team for lk in pl.teams] == info['teams'] and len(pl.teams) == 5
    assert pl.skills == info['skills'] and pl.fields['nationality'] == info['nationality']
    assert os.path.isfile(os.path.join(folder, pl.photo))
    assert not original_player.changes(pl, folder).any


def test_unchanged_original_player_changes_nothing(game, catalog, assets):
    folder, save_image = assets
    pl = entry(game, catalog, MESSI, 'jg_messi', save_image)
    project = model.Project(players=[pl])
    assert not validation.has_errors(validation.validate(project, catalog, folder))
    result = builder.build(project, game, folder)
    assert result.database == builder.build(model.Project(), game, folder).database
    assert not result.loose and result.assigned_player_ids == {}


def test_edited_original_player(game, catalog, assets):
    """Only what changed goes to the player's own row; a generic head drops the scanned one."""
    folder, save_image = assets
    pl = entry(game, catalog, XAVI, 'jg_xavi', save_image)
    pl.last_name, pl.height = 'Hernández Creus', 175
    pl.skills = {**pl.skills, 'PAS': 99}
    pl.generic = True
    db = t3db.Database(builder.build(model.Project(players=[pl]), game, folder).database, game.meta)
    row = rows_of(db, 'players', 'playerid', XAVI)[0]
    names = db.by_name('playernames')
    text = {names.value(r, names.field('nameid')): r[1] for r in names.records}
    assert text[value(db, 'players', row, 'lastnameid')] == 'Hernández Creus'.encode('utf-8')
    assert value(db, 'players', row, 'height') == 175 and value(db, 'players', row, 'fspassing') == 99
    assert value(db, 'players', row, 'headclasscode') == 1
    assert value(db, 'players', row, 'weight') == catalog.players_by_id[XAVI]['weight']


def test_real_face_needs_a_six_digit_playerid(game, catalog, assets):
    folder, save_image = assets
    pl = entry(game, catalog, XAVI, 'jg_xavi', save_image)
    pl.generic, pl.face = False, model.ScannedFace(source_id=1)
    codes = {i.code for i in validation.validate(model.Project(players=[pl]), catalog, folder)}
    assert 'face_needs_six_digits' in codes


def test_players_in_several_teams(game, catalog):
    """A player in several teams (one teamplayerlinks row each, own number and position): two new clubs, a new club
    + a national team (a team of the game, once one of its players leaves it), only a national team, one of the
    game's players added to a new team; a game player left with no team stays as a free agent."""
    project = load_palmeiras()
    palmeiras = project.teams[0]
    other = palmeiras.model_copy(update={'uid': 'tm_02', 'name': 'Corinthians', 'lineups': []})
    project.teams.append(other)
    roster = project.roster(palmeiras.uid)
    both, keeper, national = roster[0], roster[1], roster[2]
    both.teams.append(model.TeamLink(team='tm_02', number=9))
    messi = entry(game, catalog, MESSI, 'jg_messi')
    messi.teams.append(model.TeamLink(team='tm_02', number=30))
    squad = {p['id']: p for p in catalog.players if BRAZIL in p['teams']}
    brazil_keeper = next(pid for pid, p in squad.items() if p['position'] == 0)
    brazil_striker = next(pid for pid, p in squad.items() if p['position'] != 0 and len(p['teams']) == 1)
    keeper.teams.append(model.TeamLink(team=BRAZIL, number=1, position=0))
    national.teams = [model.TeamLink(team=BRAZIL, number=99, position=25)]  # leaves Palmeiras, Brazil only
    project.players += [messi]
    codes = {(i.code, i.field) for i in validation.validate(project, catalog, PALMEIRAS) if i.severity == 'error'}
    assert ('team_full', 'teams.1') in codes and ('team_full', 'teams.0') in codes  # Brazil already has 13
    leaving = [entry(game, catalog, pid, f'jg_{pid}') for pid in (brazil_keeper, brazil_striker)]
    for pl in leaving:
        pl.teams = [lk for lk in pl.teams if lk.team != BRAZIL]
    project.players += leaving
    issues = validation.validate(project, catalog, PALMEIRAS)
    assert not validation.has_errors(issues), [i for i in issues if i.severity == 'error']

    result = builder.build(project, game, PALMEIRAS)
    db = t3db.Database(result.database, game.meta)
    pid = result.assigned_player_ids
    tid = {t.uid: result.assigned_team_ids[t.uid] for t in project.teams}
    assert MESSI not in pid.values() and len(rows_of(db, 'players', 'playerid', pid[both.uid])) == 1
    assert set(links_of(db, pid[both.uid])) == {tid[palmeiras.uid], tid['tm_02']}
    assert links_of(db, pid[both.uid])[tid['tm_02']][0] == 9
    assert links_of(db, MESSI)[tid['tm_02']][0] == 30 and len(links_of(db, MESSI)) == 6
    assert links_of(db, pid[keeper.uid])[BRAZIL] == (1, 0) and links_of(db, pid[national.uid]) == {BRAZIL: (99, 25)}
    brazil_now = [value(db, 'teamplayerlinks', r, 'playerid') for r in rows_of(db, 'teamplayerlinks', 'teamid', BRAZIL)]
    assert len(brazil_now) == len(squad) and not {brazil_keeper, brazil_striker} & set(brazil_now)
    assert not links_of(db, brazil_striker)  # no team left: a free agent
    assert len(links_of(db, brazil_keeper)) == len(squad[brazil_keeper]['teams']) - 1
    keys = [value(db, 'teamplayerlinks', r, 'artificialkey') for r in db.by_name('teamplayerlinks').records]
    assert len(keys) == len(set(keys))


def test_roles_of_a_player_who_leaves_go_to_who_joins(game, catalog):
    """The captain leaves an original team (his entry drops it) and a project player joins: the captaincy goes to
    the player who joined; an edited original team's lineup can name him."""
    from fsmod import original_team
    captain = next(t for t in catalog.teams if t['id'] == BARCELONA)['captain']
    leaving = entry(game, catalog, captain, 'jg_cap')
    leaving.teams = [lk for lk in leaving.teams if lk.team != BARCELONA]
    player = model.Player(uid='jg_x', first_name='Novo', last_name='Jogador', teams=[model.TeamLink(team=BARCELONA)])
    project = model.Project(players=[player, leaving])
    result = builder.build(project, game, PALMEIRAS)
    db = t3db.Database(result.database, game.meta)
    new = result.assigned_player_ids['jg_x']
    assert value(db, 'teams', rows_of(db, 'teams', 'teamid', BARCELONA)[0], 'captainid') == new
    assert BARCELONA in links_of(db, new) and BARCELONA not in links_of(db, captain)

    tm = original_team.load(game, catalog, BARCELONA, 'tm_barca', lambda name, data: None)
    tm.crest, tm.loaded.images = None, {}
    tm.use_real_kits = tm.loaded.team['use_real_kits']
    tm.captain = 'jg_x'
    tm.lineups = [model.Lineup(players=5, goalkeeper=True, starters=[None, 'jg_x'])]
    project.teams = [tm]
    issues = validation.validate(project, catalog, PALMEIRAS)
    assert not [i for i in issues if i.severity == 'error' and i.entity != tm.uid or i.code == 'captain_not_in_roster']
