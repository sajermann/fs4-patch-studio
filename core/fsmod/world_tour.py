"""Players the user picks for the World Tour friendly match (Project.world_tour), whose teams feed the screen where the
user adds players to the squad.

How the game fills that screen: when the World Tour starts it creates the teams Dark (4000) and White (4001) in the save,
and tops each one up to 6 with random players (the user's captain goes in Dark). After the friendly match it keeps the
first 4 rows of each team and offers them, so at most 3 + 4 can be chosen: the captain must stay in the first 4 of Dark.

Creating a team removes its whole squad, and the screen that starts the World Tour clears both teams. So a team with
picked players goes into the database ready (rows of fsmod.world_tour_rows and its texts), and that screen's call is
switched off (fsmod.gamepatches). A team with no picks is left for the game to create, as usual.

A player comes in one of two ways:
  original  the player himself. No level or skills to buy (the game only gives those to created players).
  clone     a copy with his own playerid and created-player rows: he has a level and skills to buy, and his original
            stays in his club. A created player cut from a team is deleted from the game, so an original can never get
            those rows. The clone keeps a scanned head by having the original's files under his id (and player.lua
            changed, fsmod.gamepatches), but the menus do not show his photo.
"""
import itertools

from . import chunk, photo, scanface
from .world_tour_rows import CREATED_PLAYER_ROWS, TEAM_ROWS

DARK, WHITE = 4000, 4001
TEAMS = {'dark': (DARK, 'Dark'), 'white': (WHITE, 'White')}  # field of model.WorldTour: (teamid, name)
GENERATED_POSITION = 27  # teamplayerlinks.position of the game's generated players
FIRST_JERSEY = {DARK: 2, WHITE: 1}  # the captain takes number 1 in Dark
CAPTAIN_FIELD = 'captainid'
TAKER_FIELDS = ('penaltytakerid', 'freekicktakerid', 'longkicktakerid', 'leftcornerkicktakerid', 'rightcornerkicktakerid')
TEXT_KEYS = ('TeamName', 'CT_TeamName', 'TeamName_Abbr15', 'TeamName_Abbr10', 'TeamName_Abbr7')  # not Abbr3: it would
# hide, in the match scoreboard, the abbreviation the user gives the team


class WorldTourError(ValueError):
    pass


def _empty_row(table):
    """(row, raw record) with every field zeroed."""
    row = []
    for f in table.fields:
        if f.type == 0:
            row.append(bytes(f.depth // 8))
        else:
            row.append(None if f.type in (13, 14) else 0)
    return row, bytes(table.rec_size)


def _append(db, name, values):
    """New row of a table from {field: value}; other fields zero."""
    table = db.table(name)
    row, raw = _empty_row(table)
    for field, value in values.items():
        db.put_any(table, row, field, value)
    db.append(name, row, raw)


def _files_of(game, name, loose, entries):
    """Bytes of a file as this build leaves it: the project's face or photo when it has one, else the game's."""
    if name in loose:
        return loose[name]
    for (_, entry), data in entries.items():
        if entry == name:
            return data
    found = game.read_entry(name)
    return found[2] if found else None


def clone_files(game, source, clone, loose, entries):
    """{loose file name: bytes} of a clone: the scanned head and the photo of source under the clone's id."""
    files = {}
    for template in scanface.FILES.values():
        data = _files_of(game, scanface.ASSETS + template.format(source), loose, entries)
        if data is not None:
            # names inside the file may have no '_' after the id (hairlod_<id>player_hair...), and the id alone could
            # be part of another number
            renamed = scanface.renamed(chunk.decode(data), f'_{source}', f'_{clone}')
            files[scanface.ASSETS + template.format(clone)] = chunk.chunkzip(renamed)
    picture = loose.get(photo.photo_name(source))
    if picture is None and source in game.photo_index:
        picture = game.read_photo(source)[1]
    if picture is not None:
        files[photo.photo_name(clone)] = picture
    return files


def _add_clone(db, source):
    """Copy of a player with the next free playerid and the rows of a created player. Returns his id."""
    players = db.table('players')
    rows = db.rows('players', 'playerid', source)
    if not rows:
        raise WorldTourError(f'player {source} does not exist')
    clone = db.max_value('players', 'playerid') + 1
    row = list(players.records[rows[0]])
    db.put(players, row, 'playerid', clone)
    db.insert_sorted('players', 'playerid', row, players.raw_records[rows[0]])
    kits = db.table('playerkit')
    for k in db.rows('playerkit', 'playerid', source):
        kit = list(kits.records[k])
        db.put(kits, kit, 'playerid', clone)
        db.append('playerkit', kit, kits.raw_records[k])
    _append(db, 'createplayer', {**CREATED_PLAYER_ROWS['createplayer'], 'create_playerid': clone})
    _append(db, 'playerperks', {**CREATED_PLAYER_ROWS['playerperks'], 'playerid': clone})
    return clone


def _add_links(db, teamid, roster):
    links = db.table('teamplayerlinks')
    for number, playerid in enumerate(roster, FIRST_JERSEY[teamid]):
        row = list(links.records[0])
        db.put(links, row, 'teamid', teamid)
        db.put(links, row, 'playerid', playerid)
        db.put(links, row, 'position', GENERATED_POSITION)
        db.put(links, row, 'jerseynumber', number)
        db.put(links, row, 'artificialkey', db.max_value('teamplayerlinks', 'artificialkey') + 1)
        db.append('teamplayerlinks', row, links.raw_records[0])


def _add_team(db, teamid, roster, captain):
    rows = TEAM_ROWS[teamid]
    teams = db.table('teams')
    new, raw = list(teams.records[0]), teams.raw_records[0]
    for field, value in rows['teams'][0].items():
        db.put_any(teams, new, field, value)
    db.put(teams, new, CAPTAIN_FIELD, captain)
    for field, playerid in zip(TAKER_FIELDS, itertools.cycle(roster)):
        db.put(teams, new, field, playerid)
    db.insert_sorted('teams', 'teamid', new, raw)
    for values in rows['cz_teams']:
        _append(db, 'cz_teams', values)
    for values in rows['cz_teamkits']:
        _append(db, 'cz_teamkits', {**values, 'artificialkey': len(db.table('cz_teamkits').records)})
    leagues = db.table('leagueteamlinks')
    for values in rows['leagueteamlinks']:
        row, raw = list(leagues.records[0]), leagues.raw_records[0]
        for field, value in values.items():
            db.put_any(leagues, row, field, value)
        db.put(leagues, row, 'tableposition', len(db.rows('leagueteamlinks', 'leagueid', values['leagueid'])) + 1)
        db.put(leagues, row, 'artificialkey', db.max_value('leagueteamlinks', 'artificialkey') + 1)
        db.append('leagueteamlinks', row, raw)
    stadiums = db.table('teamstadiumlinks')
    for values in rows['teamstadiumlinks']:
        row, raw = list(stadiums.records[0]), stadiums.raw_records[0]
        for field, value in values.items():
            db.put_any(stadiums, row, field, value)
        db.append('teamstadiumlinks', row, raw)


def apply(db, game, project, player_ids, loose, entries, texts, say):
    """Puts the picked players and their teams in the database, the clones' files in loose and the team names in texts.
    Runs after every other change to the players: a clone copies his original as the project leaves him."""
    wt = project.world_tour
    rosters = {}
    for side, (teamid, name) in TEAMS.items():
        roster = []
        for slot in getattr(wt, side):
            source = player_ids[slot.player] if isinstance(slot.player, str) else slot.player
            if slot.mode == 'clone':
                pid = _add_clone(db, source)
                players = db.table('players')
                if db.get(players, players.records[db.rows('players', 'playerid', source)[0]], 'headclasscode') == 0:
                    loose.update(clone_files(game, source, pid, loose, entries))
                say(f'World Tour {name}: {pid}, clone of {source}')
            else:
                pid = source
                if not db.rows('players', 'playerid', pid):
                    raise WorldTourError(f'player {pid} does not exist')
                say(f'World Tour {name}: {pid}')
            roster.append(pid)
        if roster:
            rosters[teamid] = roster
            for key in TEXT_KEYS:
                texts[f'{key}_{teamid}'] = name
    # the game gives the captain it creates in the World Tour the next free playerid
    captain = db.max_value('players', 'playerid') + 1
    for teamid, roster in rosters.items():
        _add_links(db, teamid, roster)
        _add_team(db, teamid, roster, captain if teamid == DARK else roster[0])
