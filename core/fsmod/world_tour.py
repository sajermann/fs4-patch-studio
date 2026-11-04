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
  clone     a copy with his own playerid and created-player rows: he has a level and skills to buy, starts with the
            same skills as the created players, and his original stays in his club. A created player cut from a team is
            deleted from the game, so an original can never get those rows. The clone keeps a scanned head by having the
            original's files under his id (and player.lua changed, fsmod.gamepatches).

The game never looks for the photo of a created player: it draws his head and shows imgAssets/heads/p<id>.png, and a file
of that name beats the drawing. So a clone's photo goes there, framed for the place the screen gives a drawn image.

With no fs4lineup row the game picks each team's starters by rating, so strong picks would leave out the captain and weak
ones would sit out: a team with picks gets a row.
"""
import io
import itertools

from PIL import Image

from . import chunk, crest, photo, scanface
from .world_tour_rows import CREATED_PLAYER_ROWS, TEAM_ROWS

DARK, WHITE = 4000, 4001
TEAMS = {'dark': (DARK, 'Dark'), 'white': (WHITE, 'White')}  # field of model.WorldTour: (teamid, name)
GENERATED_POSITION = 27  # teamplayerlinks.position of the game's generated players
FIRST_JERSEY = {DARK: 2, WHITE: 1}  # the captain takes number 1 in Dark
CAPTAIN_FIELD = 'captainid'
TAKER_FIELDS = ('penaltytakerid', 'freekicktakerid', 'longkicktakerid', 'leftcornerkicktakerid', 'rightcornerkicktakerid')
CREATED_PLAYER_STATS = {'fsathleticism': 71, 'fsdefending': 71, 'fsdribbling': 71, 'fsgk': 71, 'fspassing': 71,
                        'fsshooting': 71, 'fsspeed': 71, 'skillmoves': 0, 'overallrating': 71, 'playerstylecode': 1,
                        'developmentstylecode': 1, 'developmenttypecode': 1}  # as the game writes its created players
# fifa_playerhead.big shows a .dds at _y 77, 100x100 and anything else at _y 64, 128x128, keeping the center
PHOTO_Y, PHOTO_SIZE, DRAWN_Y, DRAWN_SIZE = 77, 100, 64, 128
THUMBNAIL_CANVAS = 256
LINEUP_MODE = {'numberofplayers': 4, 'hasgoalie': 1, 'tacticsidx': 1}  # the only mode of the friendly match
LINEUP_SIDE = {DARK: 0, WHITE: 1}
TEAM_SIZE = 6  # the game tops each friendly team up to this many players
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


def clone_head_files(game, source, clone, loose, entries):
    """{loose file name: bytes} of a clone: the scanned head of source under the clone's id."""
    files = {}
    for template in scanface.FILES.values():
        data = _files_of(game, scanface.ASSETS + template.format(source), loose, entries)
        if data is not None:
            # names inside the file may have no '_' after the id (hairlod_<id>player_hair...), and the id alone could
            # be part of another number
            renamed = scanface.renamed(chunk.decode(data), f'_{source}', f'_{clone}')
            files[scanface.ASSETS + template.format(clone)] = chunk.chunkzip(renamed)
    return files


def thumbnail_name(pid):
    return photo.photo_name(pid).removesuffix('dds') + 'png'


def clone_thumbnail(game, source, loose):
    """The photo of source in a transparent square, so that it looks right at the size of a drawn image: compressed like
    p<id>.dds (the game loads it under the .png name). None when he has no photo."""
    picture = loose.get(photo.photo_name(source))
    if picture is None and source in game.photo_index:
        picture = game.read_photo(source)[1]
    if picture is None:
        return None
    image = Image.open(io.BytesIO(chunk.decode(picture))).convert('RGBA')
    margin = (DRAWN_SIZE - PHOTO_SIZE) / 2
    scale = THUMBNAIL_CANVAS / DRAWN_SIZE
    size = round(PHOTO_SIZE * scale)
    frame = Image.new('RGBA', (THUMBNAIL_CANVAS, THUMBNAIL_CANVAS))
    frame.paste(image.resize((size, size), Image.LANCZOS), (round(margin * scale), round((margin + PHOTO_Y - DRAWN_Y) * scale)))
    return crest.dds_entry(game.read_photo(min(game.photo_index))[1], frame)


def _add_clone(db, source):
    """Copy of a player with the next free playerid and the rows of a created player. Returns his id."""
    players = db.table('players')
    rows = db.rows('players', 'playerid', source)
    if not rows:
        raise WorldTourError(f'player {source} does not exist')
    clone = db.max_value('players', 'playerid') + 1
    row = list(players.records[rows[0]])
    db.put(players, row, 'playerid', clone)
    for field, value in CREATED_PLAYER_STATS.items():
        db.put(players, row, field, value)
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


def _add_lineups(db, rosters, captain):
    """fs4lineup rows of the teams with picks. Slot 0 is the goalkeeper: the best at it, the first picked among equals.
    Generated players get the next free ids (captain, Dark, then White), so a team with too few picks can name them, and
    one of them goes in goal rather than the only pick."""
    players = db.table('players')
    keeping = lambda pid: db.get(players, players.records[db.rows('players', 'playerid', pid)[0]], 'fsgk')
    size = LINEUP_MODE['numberofplayers']
    next_id = captain + 1
    for teamid, side in LINEUP_SIDE.items():
        roster = rosters.get(teamid, [])
        own = [captain] if teamid == DARK else []
        generated = list(range(next_id, next_id + TEAM_SIZE - len(roster) - len(own)))
        next_id += len(generated)
        if not roster:
            continue
        picks = sorted(roster, key=keeping, reverse=True)
        order = [*picks, *own] if len(picks) + len(own) >= size else [generated[0], *picks, *own, *generated[1:]]
        slots = {f'position{k}': pid for k, pid in enumerate(order[:size])}
        _append(db, 'fs4lineup', {'teamid': teamid, 'side': side, **LINEUP_MODE, **slots})


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
                    loose.update(clone_head_files(game, source, pid, loose, entries))
                thumbnail = clone_thumbnail(game, source, loose)
                if thumbnail is not None:
                    loose[thumbnail_name(pid)] = thumbnail
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
    _add_lineups(db, rosters, captain)
