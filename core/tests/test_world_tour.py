import pytest

from fsmod import builder, chunk, dbcrc, gamepatches, model, scanface, validation, world_tour
from fsmod.catalog import Catalog

MESSI, INIESTA, XAVI, RONALDO = 158023, 41, 10535, 20801


def build(game, tmp_path, **world_tour_data):
    project = model.load({'version': model.CONTRACT_VERSION, 'world_tour': world_tour_data})
    result = builder.build(project, game, str(tmp_path))
    return result, builder.Db(result.database, game.meta)


def squad(db, teamid):
    links = db.table('teamplayerlinks')
    return [db.get(links, links.records[k], 'playerid') for k in db.rows('teamplayerlinks', 'teamid', teamid)]


def team_row(db, teamid, field):
    teams = db.table('teams')
    return db.get(teams, teams.records[db.rows('teams', 'teamid', teamid)[0]], field)


def test_old_project_has_no_picks_and_the_game_stays_as_it_is(game, tmp_path):
    project = model.load({'version': 4})
    assert project.world_tour == model.WorldTour()
    assert project.to_json()['version'] == model.CONTRACT_VERSION
    result = builder.build(project, game, str(tmp_path))
    db = builder.Db(result.database, game.meta)
    assert not db.rows('teams', 'teamid', world_tour.DARK) and not db.rows('teamplayerlinks', 'teamid', world_tour.WHITE)
    assert ('data1.big', gamepatches.SELECT_LOCATION) not in result.entries
    assert ('data0.big', gamepatches.PLAYER_LUA) not in result.entries


def test_original_player_goes_in_the_team_and_keeps_his_clubs(game, tmp_path):
    before = builder.Db(game.original_db(), game.meta)
    result, db = build(game, tmp_path, white=[{'player': XAVI, 'mode': 'original'}])
    assert squad(db, world_tour.WHITE) == [XAVI]
    assert len(db.rows('teamplayerlinks', 'playerid', XAVI)) == len(before.rows('teamplayerlinks', 'playerid', XAVI)) + 1
    assert db.table('players').records == before.table('players').records  # no copy
    assert not db.table('createplayer').records  # a created player cut from a team is deleted from the game
    assert dbcrc.check(result.database) == []
    # no clone: player.lua stays, the screen that clears the teams does not
    assert ('data0.big', gamepatches.PLAYER_LUA) not in result.entries
    assert ('data1.big', gamepatches.SELECT_LOCATION) in result.entries


def test_clone_is_a_created_copy_with_his_own_head_files(game, tmp_path):
    before = builder.Db(game.original_db(), game.meta)
    first_free = before.max_value('players', 'playerid') + 1
    result, db = build(game, tmp_path, dark=[{'player': MESSI}])
    assert squad(db, world_tour.DARK) == [first_free]
    players = db.table('players')
    clone = players.records[db.rows('players', 'playerid', first_free)[0]]
    source = players.records[db.rows('players', 'playerid', MESSI)[0]]
    assert [f.name for f in players.fields if players.value(clone, f) != players.value(source, f)] == ['playerid']
    assert db.rows('createplayer', 'create_playerid', first_free) and db.rows('playerperks', 'playerid', first_free)
    assert not db.rows('createplayer', 'create_playerid', MESSI)
    assert len(squad(db, 241)) == len(squad(before, 241))  # the original stays in his club
    names = [scanface.ASSETS + t.format(first_free) for t in scanface.FILES.values()]
    assert set(names) <= set(result.loose)
    head = chunk.decode(result.loose[scanface.ASSETS + scanface.FILES['head'].format(first_free)])
    assert str(first_free).encode() in head and str(MESSI).encode() not in head
    lod = chunk.decode(result.loose[scanface.ASSETS + scanface.FILES['hairlod'].format(first_free)])
    assert str(MESSI).encode() not in lod  # hairlod_<id>player_hair...: no '_' after the id
    lua = chunk.decode(result.entries['data0.big', gamepatches.PLAYER_LUA])
    assert gamepatches.SCANNED_HEAD_LINES in lua


def test_short_id_only_takes_that_player_s_files(game, tmp_path):
    """_41_ is also in the kit files of team 41."""
    result, db = build(game, tmp_path, dark=[{'player': INIESTA}])
    clone = squad(db, world_tour.DARK)[0]
    assert {n for n in result.loose if f'_{clone}_' in n} == {scanface.ASSETS + t.format(clone) for t in scanface.FILES.values()}


def test_seven_clones_and_the_captain_comes_after_them(game, tmp_path):
    first = builder.Db(game.original_db(), game.meta).max_value('players', 'playerid') + 1
    _, db = build(game, tmp_path, dark=[{'player': p} for p in (MESSI, RONALDO, INIESTA)],
                  white=[{'player': p} for p in (XAVI, 13732, 5471, 7763)])
    assert squad(db, world_tour.DARK) == [first, first + 1, first + 2]
    assert squad(db, world_tour.WHITE) == [first + 3, first + 4, first + 5, first + 6]
    assert team_row(db, world_tour.DARK, 'captainid') == first + 7
    assert team_row(db, world_tour.WHITE, 'captainid') == first + 3
    assert team_row(db, world_tour.DARK, 'teamname') == 'Dark'
    links = db.table('teamplayerlinks')
    numbers = [db.get(links, links.records[k], 'jerseynumber') for k in db.rows('teamplayerlinks', 'teamid', world_tour.DARK)]
    assert numbers == [2, 3, 4]  # the captain takes 1
    assert len(db.table('cz_teams').records) == 2 and len(db.table('cz_teamkits').records) == 4


def test_a_team_with_no_picks_is_left_for_the_game_to_create(game, tmp_path):
    result, db = build(game, tmp_path, white=[{'player': XAVI, 'mode': 'original'}])
    assert db.rows('teams', 'teamid', world_tour.WHITE) and not db.rows('teams', 'teamid', world_tour.DARK)
    assert not squad(db, world_tour.DARK)
    assert len(db.table('cz_teams').records) == 1


def test_game_patch_and_clones_change_the_same_script(game, tmp_path):
    project = model.load({'version': 5, 'game_patches': {'close_up_heads': True}, 'world_tour': {'dark': [{'player': MESSI}]}})
    lua = chunk.decode(builder.build(project, game, str(tmp_path)).entries['data0.big', gamepatches.PLAYER_LUA])
    assert gamepatches.HIGH_LOD_BRANCH in lua and gamepatches.SCANNED_HEAD_LINES in lua


def test_screen_changes_only_the_name_of_the_call(game, tmp_path):
    from fsmod import leaguelogo
    entries = gamepatches.entries(game, model.GamePatches(), model.WorldTour(dark=[{'player': MESSI, 'mode': 'original'}]))
    new, _ = leaguelogo.read_bigf(chunk.decode(entries['data1.big', gamepatches.SELECT_LOCATION]))
    old, _ = leaguelogo.read_bigf(chunk.decode(game.read_entry(gamepatches.SELECT_LOCATION)[2]))
    assert [n for n, _ in new] == [n for n, _ in old]
    for (name, a), (_, b) in zip(old, new):
        if name == gamepatches.APT_CONSTANTS:
            assert leaguelogo.refpack_decode(b) == leaguelogo.refpack_decode(a).replace(gamepatches.CLEAR_TEAMS_CALL,
                                                                                          gamepatches.CLEAR_TEAMS_OFF)
        else:
            assert a == b


def test_new_player_without_team_can_be_picked(game, tmp_path):
    data = {'version': 5, 'players': [{'uid': 'p1', 'first_name': 'Ana', 'last_name': 'Lima'}],
            'world_tour': {'white': [{'player': 'p1', 'mode': 'original'}]}}
    result = builder.build(model.load(data), game, str(tmp_path))
    db = builder.Db(result.database, game.meta)
    assert squad(db, world_tour.WHITE) == [result.assigned_player_ids['p1']]
    issues = validation.validate(model.load(data), Catalog(game), str(tmp_path))
    assert 'free_agent_not_exported' not in {i.code for i in issues}


def test_hidden_new_player_is_left_out(game, tmp_path):
    data = {'version': 5, 'players': [{'uid': 'p1', 'first_name': 'Ana', 'last_name': 'Lima', 'hidden': True}],
            'world_tour': {'white': [{'player': 'p1'}]}}
    project = model.load(data)
    assert project.visible().world_tour.slots == []
    assert ('data1.big', gamepatches.SELECT_LOCATION) not in builder.build(project, game, str(tmp_path)).entries


def test_validation(game, tmp_path):
    catalog = Catalog(game)

    def codes(**wt):
        project = model.load({'version': 5, 'world_tour': wt})
        return {i.code for i in validation.validate(project, catalog, str(tmp_path)) if i.code.startswith('world_tour')}

    assert codes(dark=[{'player': MESSI}], white=[{'player': XAVI}]) == set()
    assert codes(dark=[{'player': p} for p in (MESSI, RONALDO, INIESTA, XAVI)]) == {'world_tour_team_too_large'}
    assert codes(white=[{'player': 'gone'}]) == {'world_tour_player_not_found'}
    assert codes(white=[{'player': 999999}]) == {'world_tour_player_not_found'}
    assert codes(dark=[{'player': MESSI}], white=[{'player': MESSI}]) == {'world_tour_player_repeated'}


def test_missing_player_is_a_clear_build_error(game, tmp_path):
    with pytest.raises(builder.BuildError):
        build(game, tmp_path, dark=[{'player': 999999}])
