"""Builds the whole mod (new leagues, teams and players) from a Project.

Everything is rebuilt from the ORIGINALS on every run (database, texts, images); nothing depends on
what is installed.

  - New league: a leagueid the game does not use anywhere (League.league_id, given once by the build): record in
    `leagues` + the template league's referees, texts LeagueName_<id> / LeagueName_Abbr15_<id> as new locale keys.
    The selector shows the flag of the league's COUNTRY, so every new league gets a country of its own that no
    nation uses (IMAGE_COUNTRIES) and its image is written as that country's flag (leaguelogo, loose files).
  - New team: a teamid the game does not use anywhere (Team.team_id, given once by the build). Rows are cloned
    from a generic template team; texts are new locale keys (locale.key_hash); crest and kits are loose files
    named by the teamid.
  - Original leagues/teams/stadiums (project.originals): hidden leagues leave `leagues` and their teams go to
    HIDDEN_TEAMS_LEAGUE; hidden teams too; locks are fs4unlockables_defs.is_locked of the rows the game already has
    (the game ignores new rows).
  - New players: cloned from generic players (headclasscode 1), new nameids and a playerid the game does not
    use anywhere (Player.player_id, given once by the build). Photo and real face (headclasscode 0, files named
    by the playerid) are loose files: the game opens d:/<name> from disk when no archive has it.

Output: database bytes (goes into data8.big/.bh) + new entries {(archive, entry name): bytes} that replace
entries of original game archives. write_patch() writes the whole patched archives (ReStreet 2.x has no Mods
overlay): an entry that fits stays in place, a bigger one moves to the end of the archive with its index updated.
"""
import datetime
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from PIL import Image

from . import (big, chunk, crest, dbcrc, gamepatches, kit, leaguelogo, locale, model, original_player, original_team,
               photo, preview, rx3tex, scanface, t3db)
from .game import DB_ENTRY, GAME_DATA, LOCALE_ENTRIES, LOCALE_ENTRY, LOCALE_FILES, PATCH_TARGETS

HIDDEN_LEAGUES = {382, 76, 2092, 2095, 2097}  # ids the league selector never shows
# ids some other league screen removes: never given to a new league either
SCREEN_REMOVED_LEAGUES = {390, 78, 384, 2000, 2028}
TEMPLATE_LEAGUE = 39  # MLS: record and referees of every new league
# league 2095 "Street Video-Temp": the selector hides it and it already holds hidden teams; hidden original
# leagues and teams move their teams there (no original team is leagueless; validated in game)
HIDDEN_TEAMS_LEAGUE = 2095
UNLOCKABLE_STADIUM, UNLOCKABLE_TEAM = 2, 3  # fs4unlockables_defs.type_id (fs4unlockables_types)
FIRST_NEW_LEAGUEID = 3000  # above every league text of the game (the last one is 2100)
LAST_NEW_LEAGUEID = 4096  # leagues.leagueid: 12 bits from 1
# leagues.countryid has 8 bits and the game's nations are 1-216: 217-255 are no country, so each new league takes
# one as the id of its image (validated in game). Nations without a league of the game could
# also serve (~200 more), not needed so far.
IMAGE_COUNTRIES = range(217, 256)
STREET_SLOTS = {'top': 5, 'bottom': 2, 'sock': 2}  # teamkits *_geo_type_N / *_texture_pattern_N slots
EPOCH = datetime.date(1582, 10, 14)
MAX_ROSTER = 13
# teams of a league (new + original): the team selector loads every crest of the open league on both sides at
# once and, past ~36, some do not load when coming back from the next screen (stress test 23/10, 36 validated)
MAX_LEAGUE_TEAMS = 30
# progress steps, in order: build() reports the first five, write_patch() the last one
BUILD_STEPS = ('database', 'leagues', 'teams', 'images', 'texts', 'files')
FIRST_NEW_TEAMID = 150000
LAST_NEW_TEAMID = 262144  # teams.teamid: 18 bits from 1
FIRST_NEW_PLAYERID = 206656
LAST_NEW_PLAYERID = 524287  # players.playerid has 19 bits; scanface needs 6 digits (>= 100000)
SKILL_FIELDS = {'ATH': 'fsathleticism', 'DEF': 'fsdefending', 'DRI': 'fsdribbling', 'GK': 'fsgk',
                'PAS': 'fspassing', 'SHO': 'fsshooting', 'SPE': 'fsspeed', 'TRI': 'skillmoves',
                'overall': 'overallrating'}
TEAM_TEXT_KEYS = {'name': 'TeamName_{}', 'short_name': 'TeamName_Abbr15_{}', 'name_10': 'TeamName_Abbr10_{}',
                  'name_7': 'TeamName_Abbr7_{}', 'abbreviation': 'TeamName_Abbr3_{}'}
LINEUP_SLOTS = 13  # fs4lineup position0..12
BENCH_POSITION = 28  # teamplayerlinks.position SUB (catalog.POSITIONS)
TAKER_FIELDS = ('captainid', 'penaltytakerid', 'freekicktakerid', 'leftcornerkicktakerid',
                'rightcornerkicktakerid', 'longkicktakerid')
TAKER_ROLES = original_team.TAKER_ROLES  # model.TakerRole -> teams column


def lineup_order(lineup, roster_uids):
    """Player uids of a fs4lineup row, slot by slot: the starters the lineup gives, empty or invalid
    slots filled with the next free player (its reserves first, then roster order), then the bench. Players
    not in roster_uids (hidden, moved to another team) are skipped; a short roster leaves the last slots empty."""
    pool = [u for u in [*lineup.reserves, *roster_uids] if u in roster_uids]
    starters, used = [], set()
    for u in lineup.starters[:lineup.players]:
        ok = u in roster_uids and u not in used
        starters.append(u if ok else None)
        if ok:
            used.add(u)
    pool = list(dict.fromkeys(u for u in pool if u not in used))
    order = [u if u is not None else (pool.pop(0) if pool else None) for u in starters]
    order = [u for u in order if u is not None] + pool
    return order[:LINEUP_SLOTS]


def _lineup_rows(db, tid, lineups, pids, roster_uids):
    """fs4lineup rows of a team. pids: player ref (project uid or the game's playerid) -> playerid."""
    t = db.table('fs4lineup')
    for lineup in lineups:
        order = [pids[u] for u in lineup_order(lineup, roster_uids)]
        for side in (0, 1):  # both sides of a match
            row = [0] * len(t.fields)
            for f, v in (('teamid', tid), ('side', side), ('numberofplayers', lineup.players),
                         ('hasgoalie', int(lineup.goalkeeper)), ('tacticsidx', lineup.tactic)):
                db.put(t, row, f, v)
            for k in range(LINEUP_SLOTS):
                db.put(t, row, f'position{k}', order[k] if k < len(order) else 0)
            db.append('fs4lineup', row, bytes(t.rec_size))


class BuildError(Exception):
    def __init__(self, message, entity=None):
        super().__init__(message)
        self.entity = entity  # uid of the league/team/player the error refers to


@dataclass
class BuildResult:
    database: bytes
    entries: dict  # {(archive short name, entry name): bytes}, e.g. ('data1.big', 'data/ui/.../l1439.dds')
    assigned_league_ids: dict = field(default_factory=dict)  # {league uid: leagueid} given during this build
    assigned_team_ids: dict = field(default_factory=dict)  # {team uid: teamid} given during this build
    assigned_player_ids: dict = field(default_factory=dict)  # {player uid: playerid} given during this build
    loose: dict = field(default_factory=dict)  # {internal name: bytes} written as loose files under Game/
    log: list = field(default_factory=list)


# ---------------------------------------------------------------- database helpers
class Db:
    """Thin helper over t3db with human values and row cloning/insertion."""

    def __init__(self, data, meta):
        self.db = t3db.Database(data, meta)

    def table(self, name):
        return self.db.by_name(name)

    @staticmethod
    def get(table, row, field_name):
        return table.value(row, table.field(field_name))

    @staticmethod
    def put(table, row, field_name, value):
        f = table.field(field_name)
        i = table.fields.index(f)
        if f.type == 0:
            row[i] = value.encode('utf-8').ljust(f.depth // 8, b'\0')[:f.depth // 8]
        elif f.type in (13, 14):
            row[i] = value.encode('utf-8')
        else:
            raw = int(value) - f.rangelow
            if not 0 <= raw < (1 << f.depth):
                raise BuildError(f'{table.name}.{field_name} = {value} is out of range')
            row[i] = raw

    def rows(self, table_name, field_name, value):
        t = self.table(table_name)
        f = t.field(field_name)
        return [k for k, r in enumerate(t.records) if t.value(r, f) == value]

    def insert_sorted(self, table_name, key, row, raw):
        t = self.table(table_name)
        f = t.field(key)
        v = t.value(row, f)
        pos = next((k for k, r in enumerate(t.records) if t.value(r, f) > v), len(t.records))
        t.records.insert(pos, row)
        t.raw_records.insert(pos, raw)

    def append(self, table_name, row, raw):
        t = self.table(table_name)
        t.records.append(row)
        t.raw_records.append(raw)

    def max_value(self, table_name, field_name):
        t = self.table(table_name)
        f = t.field(field_name)
        return max((t.value(r, f) for r in t.records), default=0)


# ---------------------------------------------------------------- ids
def reserved_team_ids(original_ids, locale_keys):
    """Teamids a new team must not take: teams of the database and every id with team texts (FIFA 12 teams)."""
    ids = set(original_ids)
    for k in locale_keys:
        m = re.fullmatch(r'(?:CT_)?TeamName_(?:Abbr\d+_)?(\d+)', k)
        if m:
            ids.add(int(m.group(1)))
    return ids


def team_id_is_free(game, teamid):
    """No team file of teamid in the game archives (an archive entry would win over the loose file)."""
    names = [crest.ui_crest_name(label, teamid) for label, _ in crest.UI_SIZES] + [crest.scene_crest_name(teamid)]
    names += [n(teamid, kind) for kind in (0, 1, 2) for n in (kit.kit_name, kit.thumbnail_name)]
    return not any(game.locate(n) for n in names)


def assign_team_ids(project, reserved, is_free=lambda teamid: True):
    """{team uid: teamid} for the teams without team_id: the smallest free ids from FIRST_NEW_TEAMID."""
    used = set(reserved) | {t.team_id for t in project.new_teams if t.team_id is not None}
    out, tid = {}, FIRST_NEW_TEAMID
    for tm in project.new_teams:
        if tm.team_id is not None:
            continue
        while tid in used or not is_free(tid):
            tid += 1
        if tid > LAST_NEW_TEAMID:
            raise BuildError(f'{tm.name}: no free teamid left', tm.uid)
        out[tm.uid] = tid
        used.add(tid)
    return out


def reserved_league_ids(original_ids, locale_keys):
    """Leagueids a new league must not take: leagues of the database, ids some screen hides and every id with
    league texts (FIFA 12 leagues)."""
    ids = set(original_ids) | HIDDEN_LEAGUES | SCREEN_REMOVED_LEAGUES
    for k in locale_keys:
        m = re.fullmatch(r'LeagueName_(?:Abbr\d+_)?(\d+)', k)
        if m:
            ids.add(int(m.group(1)))
    return ids


def assign_league_ids(project, reserved):
    """{league uid: leagueid} for the leagues without league_id: the smallest free ids from FIRST_NEW_LEAGUEID."""
    used = set(reserved) | {lg.league_id for lg in project.leagues if lg.league_id is not None}
    out, lid = {}, FIRST_NEW_LEAGUEID
    for lg in project.leagues:
        if lg.league_id is not None:
            continue
        while lid in used:
            lid += 1
        if lid > LAST_NEW_LEAGUEID:
            raise BuildError(f'{lg.name}: no free leagueid left', lg.uid)
        out[lg.uid] = lid
        used.add(lid)
    return out


def apply_original_changes(db, changes):
    """Hides original leagues/teams and sets the locks of original teams/stadiums (project.originals)."""
    leagues, links, defs = db.table('leagues'), db.table('leagueteamlinks'), db.table('fs4unlockables_defs')
    position = len(db.rows('leagueteamlinks', 'leagueid', HIDDEN_TEAMS_LEAGUE))

    def hide(link_rows):
        nonlocal position
        for k in link_rows:
            position += 1
            db.put(links, links.records[k], 'leagueid', HIDDEN_TEAMS_LEAGUE)
            db.put(links, links.records[k], 'tableposition', position)

    for lid in changes.hidden_leagues:
        rows = db.rows('leagues', 'leagueid', lid)
        if not rows or lid in HIDDEN_LEAGUES:
            raise BuildError(f'original league {lid} cannot be hidden')
        hide(db.rows('leagueteamlinks', 'leagueid', lid))
        del leagues.records[rows[0]]
        del leagues.raw_records[rows[0]]
    for tid in changes.hidden_teams:
        rows = db.rows('leagueteamlinks', 'teamid', tid)
        if not rows:
            raise BuildError(f'original team {tid} not found')
        hide(rows)
    for kind, locks in ((UNLOCKABLE_TEAM, changes.team_locks), (UNLOCKABLE_STADIUM, changes.stadium_locks)):
        for item, locked in locks.items():
            rows = [k for k in db.rows('fs4unlockables_defs', 'item_id', item)
                    if db.get(defs, defs.records[k], 'type_id') == kind]
            if not rows:
                raise BuildError(f'{"team" if kind == UNLOCKABLE_TEAM else "stadium"} {item} cannot be locked')
            for k in rows:
                db.put(defs, defs.records[k], 'is_locked', 1 if locked else 0)


def template_sources(project, team_links):
    """{player uid: (template playerid, template jersey number, template position, team uid)}: where each new
    player's unset values come from. Same rule as build(): the player's own `template`, otherwise the k-th player
    of the template team of his first new team (cycling); number and position are those of his link to that team
    (team uid). Players only in the game's teams cycle through the default template team (no number/position:
    those come from the game team). team_links(teamid) -> [(playerid, number, position)] in database order.
    Free agents only have a source when they set `template` (they are not built)."""
    out = {}
    for tm in project.new_teams:
        links = team_links(tm.template)
        for k, pl in enumerate(project.roster(tm.uid)):
            if not links or pl.uid in out or pl.is_original:
                continue
            pid, number, position = links[k % len(links)]
            out[pl.uid] = (pl.template if pl.template is not None else pid, number, position, tm.uid)
    links = team_links(model.DEFAULT_TEMPLATE_TEAM)
    for k, pl in enumerate(pl for pl in project.new_players if pl.uid not in out and pl.teams):
        out[pl.uid] = (pl.template if pl.template is not None else links[k % len(links)][0], None, None, None)
    for pl in project.new_players:
        if pl.uid not in out and pl.template is not None:
            out[pl.uid] = (pl.template, None, None, None)
    return out


def reserved_player_ids(original_ids, game):
    """Playerids a new player must not take: original players and every id with a photo or a scanned head in the
    game archives (an archive entry would win over the new player's loose file)."""
    return set(original_ids) | set(game.photo_index)


def assign_player_ids(project, reserved):
    """{player uid: playerid} for the players without player_id: the smallest ids from FIRST_NEW_PLAYERID that
    are neither reserved nor already in the project. Ids stay with the player once written back."""
    used = set(reserved) | {p.player_id for p in project.players if p.player_id is not None}
    out, pid = {}, FIRST_NEW_PLAYERID
    for pl in project.new_players:
        if pl.player_id is not None:
            continue
        while pid in used:
            pid += 1
        if pid > LAST_NEW_PLAYERID:
            raise BuildError(f'{pl.shown_name}: no free playerid left', pl.uid)
        out[pl.uid] = pid
        used.add(pid)
    return out


def _kit_files(game, tid, kind_n, colors, crest_img):
    """(files, log lines) of one kit of a new team (runs in the image pool)."""
    lines = []
    files = kit.build(game, tid, kind_n, colors['jersey'], colors['shorts'], crest_img, erase_original_badge=True,
                      log=lines.append)
    return files, lines


def _real_kit_files(game, tid, kind_n, real, assets_dir, crest_img, uid):
    """(files, log lines) of one real kit (fsmod.kit.build_real; runs in the image pool)."""
    lines = []
    images = {}
    for part in model.REAL_KIT_FILES:
        path = getattr(real, part)
        if path:
            try:
                images[part] = Image.open(os.path.join(assets_dir, path))
                images[part].load()
            except OSError as e:
                raise BuildError(f'cannot read kit image {path}: {e}', uid) from e
    files = kit.build_real(game, tid, kind_n, images['jersey'], images['shorts'], images.get('thumbnail'), crest_img,
                           log=lines.append)
    return files, lines


def _kit_color_fields(db, table, row, colors):
    """teamkits colors of a generic kit ({'jersey'|'shorts'|'socks': RGB})."""
    for part, key in (('top', 'jersey'), ('bottom', 'shorts'), ('sock', 'socks')):
        for which in ('primary', 'secondary', 'tertiary'):
            # secondary = trim: shorts use the jersey color, the others use the shorts color
            c = colors[key] if which != 'secondary' else (colors['jersey'] if key == 'shorts' else colors['shorts'])
            for ch, v in zip('rgb', c):
                db.put(table, row, f'{part}_color_{which}_{ch}', v)
    for ch, v in zip('rgb', colors['jersey']):
        db.put(table, row, f'teamcolorprim{ch}', v)


def _street_kit_fields(db, table, row, street):
    """teamkits fields of the street pieces a StreetKit sets (None or a missing part keeps the row's)."""
    for part, col in (('top', 'top'), ('bottom', 'bottom'), ('socks', 'sock')):
        piece = street and getattr(street, part)
        if not piece:
            continue
        # the game picks one of the slots at random: the same piece in all of them fixes it
        for n in range(1, STREET_SLOTS[col] + 1):
            db.put(table, row, f'{col}_geo_type_{n}', piece.style)
            db.put(table, row, f'{col}_texture_pattern_{n}', piece.pattern)
        for which, c in zip(('primary', 'secondary', 'tertiary'), piece.colors):
            for ch, v in zip('rgb', c):
                db.put(table, row, f'{col}_color_{which}_{ch}', v)


def _real_kit_fields(db, table, row, real):
    """teamkits fields of a real kit: name/number colors, collar, front number."""
    for ch, v in zip('rgb', real.name_color):
        db.put(table, row, f'jerseynamecolor{ch}', v)
    db.put(table, row, 'numbercolor', real.number_color)
    db.put(table, row, 'shortsnumbercolor', real.shorts_number_color)
    db.put(table, row, 'jerseycollargeometrytype', real.collar)
    db.put(table, row, 'jerseyfrontnumberplacementcode', 1 if real.front_number else 0)
    if real.shorts_number is not None:
        db.put(table, row, 'shortsnumberplacementcode', 1 if real.shorts_number else 0)


def free_number(used):
    """Smallest shirt number from 1 that is not in used."""
    return next(n for n in range(1, 100) if n not in used)


def _game_team_squad(db, tid, leave, update, join, entity):
    """Changes to the squad of one of the game's teams (teamplayerlinks). leave: playerids whose row is deleted (they
    stay in their other teams; none left = a free agent); update: {playerid: (number, position)} of rows that stay
    (None = keep); join: [(playerid, number, position)] new rows (copy of one of the team's rows; number None = a
    free one). Captain and set-piece roles of a player who left go to the first player who joined (the one taking his
    place), else to the team's first player."""
    links, teams = db.table('teamplayerlinks'), db.table('teams')
    team_rows = db.rows('teams', 'teamid', tid)
    if not team_rows:
        raise BuildError(f'team {tid} does not exist', entity)
    team_row = teams.records[team_rows[0]]
    rows = db.rows('teamplayerlinks', 'teamid', tid)
    model_k = rows[0] if rows else 0
    model_row, model_raw = list(links.records[model_k]), links.raw_records[model_k]
    for k in sorted((k for k in rows if db.get(links, links.records[k], 'playerid') in leave), reverse=True):
        del links.records[k], links.raw_records[k]
    for k in db.rows('teamplayerlinks', 'teamid', tid):
        row = links.records[k]
        for f, v in zip(('jerseynumber', 'position'), update.get(db.get(links, row, 'playerid'), ())):
            if v is not None:
                db.put(links, row, f, v)
    for pid, number, position in join:
        row = list(model_row)
        db.put(links, row, 'teamid', tid)
        db.put(links, row, 'playerid', pid)
        db.put(links, row, 'artificialkey', db.max_value('teamplayerlinks', 'artificialkey') + 1)
        if number is None:
            number = free_number({db.get(links, links.records[k], 'jerseynumber')
                                  for k in db.rows('teamplayerlinks', 'teamid', tid)})
        db.put(links, row, 'jerseynumber', number)
        if position is not None:
            db.put(links, row, 'position', position)
        db.append('teamplayerlinks', row, model_raw)
    squad = [db.get(links, links.records[k], 'playerid') for k in db.rows('teamplayerlinks', 'teamid', tid)]
    heir = join[0][0] if join else (squad[0] if squad else None)
    for f in TAKER_FIELDS:
        if db.get(teams, team_row, f) in leave and heir is not None:
            db.put(teams, team_row, f, heir)


def _build_original_team(db, game, tm, assets_dir, league_id, texts, say, player_ids):
    """Applies an original team entry (Team.original_id) to the game's own rows, texts and files, only where it
    differs from what was loaded (original_team.changes). player_ids: {new player uid: playerid}. Returns the jobs
    that make its image files (() -> ({internal name: bytes}, log lines)), run in the image pool."""
    tid = tm.original_id
    ch = original_team.changes(tm, assets_dir)
    teams = db.table('teams')
    rows = db.rows('teams', 'teamid', tid)
    if not rows:
        raise BuildError(f'{tm.name}: original team {tid} does not exist', tm.uid)
    row = teams.records[rows[0]]
    say(f'original team {tid} "{tm.name}"' + ('' if ch.any else ' (unchanged)'))
    if 'name' in ch.texts:
        db.put(teams, row, 'teamname', tm.name[:30])
        texts[f'CT_TeamName_{tid}'] = tm.name
    for attr in ch.texts:
        texts[TEAM_TEXT_KEYS[attr].format(tid)] = getattr(tm, attr) or tm.name
    # captain and set-piece takers (Player.ref), written only where they differ and the player is in the team
    links = db.table('teamplayerlinks')
    squad = [db.get(links, links.records[k], 'playerid') for k in db.rows('teamplayerlinks', 'teamid', tid)]
    for f, ref in (('captainid', tm.captain), *((TAKER_ROLES[r], p) for r, p in tm.takers.items())):
        pid = player_ids.get(ref) if isinstance(ref, str) else ref
        if pid in squad and pid != db.get(teams, row, f):
            db.put(teams, row, f, pid)
    if tm.lineups:
        ref_of = {pid: uid for uid, pid in player_ids.items()}
        refs = [ref_of.get(pid, pid) for pid in squad]
        _lineup_rows(db, tid, tm.lineups, dict(zip(refs, squad)), refs)
    if ch.colors:
        for n, rgb in (('1', tm.primary_color), ('2', tm.secondary_color)):
            for c, v in zip('rgb', _rgb(rgb, f'teamcolor{n}', tm.uid)):
                db.put(teams, row, f'teamcolor{n}{c}', v)
    if ch.league:
        links = db.table('leagueteamlinks')
        for k in db.rows('leagueteamlinks', 'teamid', tid):
            db.put(links, links.records[k], 'leagueid', league_id)
            db.put(links, links.records[k], 'tableposition', len(db.rows('leagueteamlinks', 'leagueid', league_id)))

    team_kits = db.table('teamkits')
    kit_rows = {db.get(team_kits, r, 'teamkittypetechid'): r for r in team_kits.records
                if db.get(team_kits, r, 'teamtechid') == tid}
    for kind, n in original_team.STREET_KINDS:
        if kind in ch.street_kits and n in kit_rows:
            _street_kit_fields(db, team_kits, kit_rows[n], tm.street_kits.get(kind))

    jobs = []
    crest_path = os.path.join(assets_dir, tm.crest) if tm.crest else None

    def crest_image():
        return Image.open(crest_path).convert('RGBA') if crest_path else Image.new('RGBA', (26, 26))

    if ch.crest and crest_path:
        jobs.append(lambda: ({**crest.ui_crest_files(game, tid, crest_image()),
                              **crest.scene_crest_files(game, tid, crest_image())}, []))
    if tm.use_real_kits:
        for kind, n in original_team.KIT_SLOTS:
            real = tm.real_kit(kind)
            parts = ch.real_kits.get(kind, set())
            if real is None:
                continue
            if 'settings' in parts and n in kit_rows:
                _real_kit_fields(db, team_kits, kit_rows[n], real)
            if 'jersey' in parts or ch.kits_mode:
                # a new jersey is a real kit of its own (crest painted in, FIFA 16 positions): built like a new team's
                thumb = real.thumbnail if 'thumbnail' in parts else None
                jobs.append(lambda n=n, real=real, thumb=thumb: _real_kit_files(
                    game, tid, n, real.model_copy(update={'thumbnail': thumb}), assets_dir, crest_image(), tm.uid))
                continue
            if 'shorts' in parts or (ch.crest and crest_path):
                # the game's own kit with the new shorts and/or crest (its jersey, crest decal and positions kept)
                jobs.append(lambda n=n, real=real, shorts='shorts' in parts: _edited_kit_files(
                    game, tid, n, os.path.join(assets_dir, real.shorts) if shorts else None,
                    crest_image() if ch.crest and crest_path else None))
            if 'thumbnail' in parts and real.thumbnail:
                jobs.append(lambda n=n, real=real: ({kit.thumbnail_name(tid, n): kit.thumbnail_dds(
                    Image.open(os.path.join(assets_dir, real.thumbnail)))}, []))
    elif ch.kits_mode or ch.kit_colors or ch.colors or ch.crest:
        for kind, n in original_team.STREET_KINDS:  # generic kits (solid colors + crest), like a new team's
            colors = tm.kit(kind)
            colors = {part: _rgb(getattr(colors, part), f'{kind}.{part}', tm.uid)
                      for part in ('jersey', 'shorts', 'socks')}
            if n in kit_rows:
                _kit_color_fields(db, team_kits, kit_rows[n], colors)
            jobs.append(lambda n=n, colors=colors: _kit_files(game, tid, n, colors, crest_image()))
    return jobs


def _archive_of(game, name):
    """Archive short name that holds a file of the game (a player photo: 2dheads.big), or None."""
    m = re.fullmatch(r'data/ui/imgassets/heads/p(\d+)\.dds', name)
    if m:
        return photo.PHOTOS_ARCHIVE if int(m.group(1)) in game.photo_index else None
    loc = game.locate(name)
    return f'data{loc[0]}.big' if loc else None


def _build_original_player(db, game, pl, assets_dir, nameid, face_templates, say):
    """Applies an original player entry (Player.original_id) to the game's own row, only where it differs from what
    was loaded (original_player.changes). Returns the jobs that make its files (photo, real face)."""
    pid = pl.original_id
    ch = original_player.changes(pl, assets_dir)
    players = db.table('players')
    rows = db.rows('players', 'playerid', pid)
    if not rows:
        raise BuildError(f'{pl.shown_name}: original player {pid} does not exist', pl.uid)
    row = players.records[rows[0]]
    before = (pl.loaded.player if pl.loaded else {})
    f = ch.fields
    say(f'original player {pid} "{pl.shown_name}"' + ('' if ch.any else ' (unchanged)'))
    try:
        if 'first_name' in f:
            db.put(players, row, 'firstnameid', nameid(pl.first_name))
        if 'last_name' in f:
            db.put(players, row, 'lastnameid', nameid(pl.last_name))
        if f & {'first_name', 'last_name', 'display_name'}:
            db.put(players, row, 'commonnameid', nameid(pl.shown_name))
        if f & {'last_name', 'jersey_name'}:
            db.put(players, row, 'playerjerseynameid', nameid(pl.jersey_name or pl.last_name))
        if 'height' in f and pl.height is not None:
            db.put(players, row, 'height', pl.height)
        if 'weight' in f and pl.weight is not None:
            db.put(players, row, 'weight', pl.weight)
        if 'birthdate' in f and pl.birthdate:
            db.put(players, row, 'birthdate', (datetime.date.fromisoformat(pl.birthdate) - EPOCH).days)
        if 'foot' in f and pl.foot:
            db.put(players, row, 'preferredfoot', 2 if pl.foot == 'left' else 1)
        for skill, v in pl.skills.items():
            if v != before.get('skills', {}).get(skill):
                db.put(players, row, SKILL_FIELDS[skill], v)
        for group, values in (('appearance', pl.appearance), ('fields', pl.fields)):
            for name, v in values.items():
                if v != before.get(group, {}).get(name):
                    db.put(players, row, name, v)
        if ch.head:
            db.put(players, row, 'headclasscode', 1 if pl.generic else 0)
    except (BuildError, ValueError, KeyError) as e:
        raise BuildError(f'{pl.shown_name}: {e}', pl.uid) from e
    jobs = []
    if ch.photo and pl.photo:
        try:
            img = Image.open(os.path.join(assets_dir, pl.photo))
            img.load()
        except OSError as e:
            raise BuildError(f'{pl.shown_name}: cannot read photo {pl.photo}: {e}', pl.uid) from e
        jobs.append(lambda: ({photo.photo_name(pid): photo.photo_file(game, img)}, []))
    if not pl.generic and pl.face is not None and (ch.head or 'appearance' in f):
        if not original_player.can_take_face(pid):
            raise BuildError(f'{pl.shown_name}: a real face needs a 6-digit playerid ({pid})', pl.uid)
        files = _face_files(pl, pid, db.get(players, row, 'haircolorcode'), game, assets_dir, face_templates)
        jobs.append(lambda: (files, []))
    return jobs


def _edited_kit_files(game, tid, kind_n, shorts_path, crest_img):
    """The game's own kit rx3 of an original team with new shorts and/or a new crest decal."""
    name = kit.kit_name(tid, kind_n)
    d = bytearray(chunk.decode(game.read_entry(name)[2]))
    if shorts_path:
        rx3tex.set_image_dxt1(d, rx3tex.by_name(d, 'shorts_cm'), Image.open(shorts_path).convert('RGB'))
    if crest_img is not None:
        rx3tex.set_image(d, rx3tex.by_name(d, 'crest_cm'), crest.square(crest_img), bg=(255, 255, 255))
    return {name: chunk.chunkzip(bytes(d))}, [f'{name}: edited']


def _face_files(pl, pid, hair_color_code, game, assets_dir, templates):
    """{loose file name: bytes} of a player's real face converted for its playerid."""
    files = scanface.read_files(scanface.project_face_dir(assets_dir, pl.uid), pl.face.source_id)
    if not templates:
        templates.update(scanface.template_files(game))
    try:
        converted = scanface.convert(templates, files, pid, preview.hair_color(hair_color_code),
                                     paint=pl.face.paint_scalp, hair_mode=pl.face.hair_mode,
                                     hair_thickness=pl.face.hair_thickness)
    except (ValueError, KeyError) as e:
        raise BuildError(f'{pl.shown_name}: face {pl.face.source_id}: {e}', pl.uid) from e
    return {scanface.ASSETS + name: chunk.chunkzip(data) for name, data in converted.items()}


def _rgb(value, what, entity):
    if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(0 <= int(x) <= 255 for x in value)):
        raise BuildError(f'{what}: invalid color {value!r} (use [R, G, B])', entity)
    return tuple(int(x) for x in value)


# ---------------------------------------------------------------- build
def build(project, game, assets_dir, log=None, progress=None):
    """Builds the mod. assets_dir = folder that image paths (crests) are relative to. Hidden leagues/teams are
    left out (Project.visible); their ids stay reserved. progress(step, done, total) is called as the build goes
    (steps: BUILD_STEPS, then write_patch's)."""
    result = BuildResult(database=b'', entries={})
    every = project
    project = project.visible()

    def say(msg):
        result.log.append(msg)
        if log:
            log(msg)

    step = progress or (lambda *_: None)
    step('database', 0, 1)
    game.ensure_complete()
    db = Db(game.original_db(), game.meta)
    step('database', 1, 1)
    locale_data = game.locale()[1]
    locale_keys = locale.keys(locale_data)
    texts, entries = {}, {}

    # ---- leagues
    leagues = db.table('leagues')
    existing = {db.get(leagues, r, 'leagueid') for r in leagues.records}
    template_league = db.rows('leagues', 'leagueid', TEMPLATE_LEAGUE)[0]
    referee_links = db.table('leaguerefereelinks')
    template_referees = db.rows('leaguerefereelinks', 'leagueid', TEMPLATE_LEAGUE)
    reserved_leagues = reserved_league_ids(existing, locale_keys)
    result.assigned_league_ids = assign_league_ids(project, reserved_leagues | {lg.league_id for lg in every.leagues})
    league_ids = {}
    if len(project.leagues) > len(IMAGE_COUNTRIES):
        raise BuildError(f'{len(project.leagues)} new leagues: at most {len(IMAGE_COUNTRIES)} (one image each)')
    for k, lg in enumerate(project.leagues):
        step('leagues', k, len(project.leagues))
        country = IMAGE_COUNTRIES[k]
        lid = lg.league_id if lg.league_id is not None else result.assigned_league_ids[lg.uid]
        if lid in reserved_leagues or lid in league_ids.values() or \
                not FIRST_NEW_LEAGUEID <= lid <= LAST_NEW_LEAGUEID:
            raise BuildError(f'{lg.name}: leagueid {lid} is not free', lg.uid)
        row = list(leagues.records[template_league])
        raw = leagues.raw_records[template_league]
        for f, v in (('leagueid', lid), ('countryid', country), ('defaultsortorder', lg.sort_order),
                     ('level', 1), ('buildupplay', 3), ('leaguename', (lg.internal_name or lg.name)[:30])):
            db.put(leagues, row, f, v)
        db.insert_sorted('leagues', 'leagueid', row, raw)
        for k in template_referees:  # matches need referees of the league
            r = list(referee_links.records[k])
            db.put(referee_links, r, 'leagueid', lid)
            db.append('leaguerefereelinks', r, referee_links.raw_records[k])
        existing.add(lid)
        league_ids[lg.uid] = lid
        texts[f'LeagueName_{lid}'] = lg.name
        texts[f'LeagueName_Abbr15_{lid}'] = lg.short_name or lg.name
        say(f'league {lid} "{lg.name}"')
        if lg.image or lg.wide_image:
            img = Image.open(os.path.join(assets_dir, lg.image or lg.wide_image)).convert('RGBA')
            wide = Image.open(os.path.join(assets_dir, lg.wide_image)).convert('RGBA') if lg.wide_image else None
            result.loose.update(leaguelogo.flag_files(game, country, img, wide, lg.wide_image_fit))  # no country: loose

    # ---- teams
    teams = db.table('teams')
    bank_teams = {db.get(teams, r, 'teamid') for r in teams.records}
    reserved_teams = reserved_team_ids(bank_teams, locale_keys)
    result.assigned_team_ids = assign_team_ids(project, reserved_teams | {t.team_id for t in every.new_teams},
                                               lambda t: team_id_is_free(game, t))
    # players: playerids no one uses in the game; photo and face go as loose files named by it
    original_pids = {db.get(db.table('players'), r, 'playerid') for r in db.table('players').records}
    reserved = reserved_player_ids(original_pids, game)
    result.assigned_player_ids = assign_player_ids(project, reserved | {p.player_id for p in every.players})
    built_pids, face_templates = set(), {}
    # the image files of the teams (photos, crests, kits: Pillow, slow with big source images) are made in a thread
    # pool while the loop edits the database (Pillow releases the GIL); jobs keeps their order for result.loose
    pool = ThreadPoolExecutor(max_workers=os.cpu_count())
    jobs = []  # futures of (files, log lines)
    names = db.table('playernames')
    used_nameids = {db.get(names, r, 'nameid') for r in names.records}
    nameid_by_text = {r[1]: db.get(names, r, 'nameid') for r in names.records if r[1]}
    free_nameid = [1]  # smallest id that may be free (ids are only taken, so it never goes down)
    players_table = db.table('players')
    original_player_rows = {}  # playerid -> row of the database's own players (new ones are appended after them)
    for k, r in enumerate(players_table.records):
        original_player_rows.setdefault(db.get(players_table, r, 'playerid'), k)
    links = db.table('teamplayerlinks')
    game_links = {}  # playerid -> first teamplayerlinks row of the game's own players
    teams_of = {}  # playerid -> teamids of the game's own players (before the build changes anything)
    for r in links.records:
        game_links.setdefault(db.get(links, r, 'playerid'), r)
        teams_of.setdefault(db.get(links, r, 'playerid'), set()).add(db.get(links, r, 'teamid'))
    player_ids = {}  # project player uid -> playerid, once his record is built
    first_position = {}  # project player uid -> position of his first team link written (default of the others)

    def nameid(text):
        b = text.encode('utf-8')
        if b in nameid_by_text:
            return nameid_by_text[b]
        names.huff.encode(b)  # validates the characters
        nid = next(i for i in range(free_nameid[0], 29000) if i not in used_nameids)
        free_nameid[0] = nid + 1
        used_nameids.add(nid)
        row = [None] * len(names.fields)
        db.put(names, row, 'nameid', nid)
        row[[f.name for f in names.fields].index('name')] = b
        db.append('playernames', row, bytes(names.rec_size))
        nameid_by_text[b] = nid
        return nid

    def build_player(pl, template_pid, where):
        """Appends the players record of a project player (cloned from template_pid unless he sets his own)."""
        players = db.table('players')
        src_pid = int(pl.template if pl.template is not None else template_pid)
        src = [original_player_rows[src_pid]] if src_pid in original_player_rows else \
            db.rows('players', 'playerid', src_pid)
        if not src:
            raise BuildError(f'{where}: template player {src_pid} does not exist', pl.uid)
        row = list(players.records[src[0]])
        raw = players.raw_records[src[0]]
        pid = pl.player_id if pl.player_id is not None else result.assigned_player_ids[pl.uid]
        if pid in reserved or pid in built_pids or not FIRST_NEW_PLAYERID <= pid <= LAST_NEW_PLAYERID:
            raise BuildError(f'{pl.shown_name}: playerid {pid} is not free', pl.uid)
        built_pids.add(pid)
        player_ids[pl.uid] = pid
        if pl.photo:
            try:
                img = Image.open(os.path.join(assets_dir, pl.photo))
                img.load()
            except OSError as e:
                raise BuildError(f'{pl.shown_name}: cannot read photo {pl.photo}: {e}', pl.uid) from e
            jobs.append(pool.submit(lambda pid=pid, img=img:
                                    ({photo.photo_name(pid): photo.photo_file(game, img)}, [])))
        try:
            db.put(players, row, 'playerid', pid)
            db.put(players, row, 'firstnameid', nameid(pl.first_name))
            db.put(players, row, 'lastnameid', nameid(pl.last_name))
            db.put(players, row, 'commonnameid', nameid(pl.shown_name))
            db.put(players, row, 'playerjerseynameid', nameid(pl.jersey_name or pl.last_name))
            if pl.height is not None:
                db.put(players, row, 'height', pl.height)
            if pl.weight is not None:
                db.put(players, row, 'weight', pl.weight)
            if pl.birthdate:
                db.put(players, row, 'birthdate', (datetime.date.fromisoformat(pl.birthdate) - EPOCH).days)
            if pl.foot:
                db.put(players, row, 'preferredfoot', 2 if pl.foot == 'left' else 1)
            for skill, v in pl.skills.items():
                db.put(players, row, SKILL_FIELDS[skill], v)
            for f, v in {**pl.appearance, **pl.fields}.items():
                db.put(players, row, f, v)
            if not pl.generic and pl.face is not None:
                db.put(players, row, 'headclasscode', 0)
        except (BuildError, ValueError, KeyError) as e:
            raise BuildError(f'{pl.shown_name}: {e}', pl.uid) from e
        if not pl.generic and pl.face is not None:
            files = _face_files(pl, pid, db.get(players, row, 'haircolorcode'), game, assets_dir, face_templates)
            jobs.append(pool.submit(lambda files=files: (files, [])))  # made here: face_templates is shared
        db.append('players', row, raw)
        say(f'   player {pid} {pl.shown_name}')
        return pid

    step('leagues', len(project.leagues), len(project.leagues))
    for k, tm in enumerate(project.new_teams):
        step('teams', k, len(project.teams))
        league_id = league_ids.get(tm.league) if isinstance(tm.league, str) else int(tm.league)
        if league_id is None or league_id not in existing:
            raise BuildError(f'{tm.name}: league {tm.league} does not exist', tm.uid)
        if not tm.crest:
            raise BuildError(f'{tm.name}: a crest is required', tm.uid)
        try:
            crest_img = Image.open(os.path.join(assets_dir, tm.crest)).convert('RGBA')
        except OSError as e:
            raise BuildError(f'{tm.name}: cannot read crest {tm.crest}: {e}', tm.uid) from e
        tid = tm.team_id if tm.team_id is not None else result.assigned_team_ids[tm.uid]
        if (tid in reserved_teams or tid in bank_teams or not FIRST_NEW_TEAMID <= tid <= LAST_NEW_TEAMID
                or not team_id_is_free(game, tid)):
            raise BuildError(f'{tm.name}: teamid {tid} is not free', tm.uid)
        say(f'team "{tm.name}" -> teamid {tid} (league {league_id})')
        primary = _rgb(tm.primary_color, 'primary_color', tm.uid)
        secondary = _rgb(tm.secondary_color, 'secondary_color', tm.uid)
        kits = {}
        for kind in ('home', 'away'):
            colors = tm.kit(kind)
            kits[kind] = {part: _rgb(getattr(colors, part), f'{kind}.{part}', tm.uid)
                          for part in ('jersey', 'shorts', 'socks')}

        # players: new ones (built the first time a team has them) and the game's own (edited entries: their own
        # record); each gets a teamplayerlinks row cloned from the k-th of the template team (number/position: the
        # link's, else the template's; a game player's own when he has a team in the game)
        template_links = [links.records[k] for k in db.rows('teamplayerlinks', 'teamid', tm.template)]
        roster = project.roster(tm.uid)
        if not 1 <= len(roster) <= MAX_ROSTER:
            raise BuildError(f'{tm.name}: a roster needs 1 to {MAX_ROSTER} players', tm.uid)
        members = [(pl.ref, pl.link(tm.uid)) for pl in roster]
        pids = {}
        for k, (pl, (ref, join)) in enumerate(zip(roster, members)):
            link = template_links[k % len(template_links)]
            link_row = list(link)
            if pl.is_original:
                pid = pl.original_id
                own = game_links.get(pid)
                if own is not None:
                    for f in ('jerseynumber', 'position'):
                        db.put(links, link_row, f, db.get(links, own, f))
            else:
                pid = player_ids.get(ref) or build_player(pl, db.get(links, link, 'playerid'), tm.name)
            pids[ref] = pid
            db.put(links, link_row, 'teamid', tid)
            db.put(links, link_row, 'playerid', pid)
            db.put(links, link_row, 'artificialkey', db.max_value('teamplayerlinks', 'artificialkey') + 1)
            if join.number is not None:
                db.put(links, link_row, 'jerseynumber', join.number)
            if join.position is not None:
                db.put(links, link_row, 'position', join.position)
            first_position.setdefault(ref, db.get(links, link_row, 'position'))
            db.append('teamplayerlinks', link_row, links.raw_records[links.records.index(link)])

        # team record and links
        ti = db.rows('teams', 'teamid', tm.template)[0]
        row = list(teams.records[ti])
        raw = teams.raw_records[ti]
        db.put(teams, row, 'teamid', tid)
        db.put(teams, row, 'assetid', tid)
        db.put(teams, row, 'teamname', tm.name[:30])
        captain = pids.get(tm.captain, pids[members[0][0]])
        db.put(teams, row, 'captainid', captain)
        for role, f in TAKER_ROLES.items():
            db.put(teams, row, f, pids.get(tm.takers.get(role), captain))
        for n, rgb in (('1', primary), ('2', secondary), ('3', primary)):
            for ch, v in zip('rgb', rgb):
                db.put(teams, row, f'teamcolor{n}{ch}', v)
        db.insert_sorted('teams', 'teamid', row, raw)
        bank_teams.add(tid)
        _lineup_rows(db, tid, tm.lineups, pids, [ref for ref, _ in members])
        for table_name in ('teamstadiumlinks', 'leagueteamlinks'):
            t = db.table(table_name)
            for k in db.rows(table_name, 'teamid', tm.template):
                r = list(t.records[k])
                db.put(t, r, 'teamid', tid)
                if table_name == 'leagueteamlinks':
                    db.put(t, r, 'leagueid', league_id)
                    db.put(t, r, 'tableposition', len(db.rows(table_name, 'leagueid', league_id)) + 1)
                    db.put(t, r, 'artificialkey', db.max_value(table_name, 'artificialkey') + 1)
                db.append(table_name, r, t.raw_records[k])
        team_kits = db.table('teamkits')
        kit_id = db.max_value('teamkits', 'teamkitid') + 1
        home_row = None
        for k in db.rows('teamkits', 'teamtechid', tm.template):
            r = list(team_kits.records[k])
            kind = 'home' if db.get(team_kits, r, 'teamkittypetechid') == 0 else 'away'
            colors = kits[kind]
            db.put(team_kits, r, 'teamtechid', tid)
            db.put(team_kits, r, 'teamkitid', kit_id)
            kit_id += 1
            _kit_color_fields(db, team_kits, r, colors)
            _street_kit_fields(db, team_kits, r, tm.street_kits.get(kind))
            real = tm.real_kit(kind)
            if real:
                _real_kit_fields(db, team_kits, r, real)
            db.append('teamkits', r, team_kits.raw_records[k])
            if kind == 'home':
                home_row = (r, team_kits.raw_records[k])
        goalkeeper = tm.real_kit('goalkeeper')
        if goalkeeper and home_row:
            # licensed teams have a goalkeeper row (teamkittypetechid 2); without it the game dresses the
            # goalkeeper with its default kit
            r = list(home_row[0])
            db.put(team_kits, r, 'teamkittypetechid', 2)
            db.put(team_kits, r, 'teamkitid', kit_id)
            kit_id += 1
            _real_kit_fields(db, team_kits, r, goalkeeper)
            db.append('teamkits', r, home_row[1])

        # texts
        defaults = {'short_name': tm.name, 'name_10': tm.name[:10], 'name_7': tm.name[:7],
                    'abbreviation': tm.name[:3].upper()}
        for attr, key in TEAM_TEXT_KEYS.items():
            texts[key.format(tid)] = getattr(tm, attr) or defaults.get(attr, tm.name)
        texts[f'CT_TeamName_{tid}'] = tm.name

        # visual files
        jobs.append(pool.submit(lambda tid=tid, img=crest_img: (
            {**crest.ui_crest_files(game, tid, img), **crest.scene_crest_files(game, tid, img)}, [])))
        for kind_n, kind in ((0, 'home'), (1, 'away'), (2, 'goalkeeper')):
            real = tm.real_kit(kind)
            if real:
                jobs.append(pool.submit(_real_kit_files, game, tid, kind_n, real, assets_dir, crest_img, tm.uid))
            elif kind != 'goalkeeper':
                jobs.append(pool.submit(_kit_files, game, tid, kind_n, kits[kind], crest_img))

    # ---- players only in the game's teams: records cloned from the default template team
    default_links = [links.records[k] for k in db.rows('teamplayerlinks', 'teamid', model.DEFAULT_TEMPLATE_TEAM)]
    for k, pl in enumerate(pl for pl in project.new_players if pl.uid not in player_ids and pl.teams):
        build_player(pl, db.get(links, default_links[k % len(default_links)], 'playerid'), pl.shown_name)

    # ---- the game's players edited in place (same playerid): their row, photo and head, only what changed
    original_jobs = set()
    for pl in project.original_players:
        for job in _build_original_player(db, game, pl, assets_dir, nameid, face_templates, say):
            future = pool.submit(job)
            jobs.append(future)
            original_jobs.add(future)

    # ---- squads of the game's teams: edited game players leave the teams they dropped and change number/position
    # in the ones they keep; new and edited players join
    squads = {}  # teamid -> (leave set, update dict, join list)
    for pl in project.original_players:
        own = teams_of.get(pl.original_id, set())
        kept = {lk.team: lk for lk in pl.teams if isinstance(lk.team, int)}
        for tid in own:
            if tid not in kept:
                squads.setdefault(tid, (set(), {}, []))[0].add(pl.original_id)
        for tid, lk in kept.items():
            if tid in own:
                squads.setdefault(tid, (set(), {}, []))[1][pl.original_id] = (lk.number, lk.position)
    for pl in project.players:
        game_teams = [lk for lk in pl.teams if isinstance(lk.team, int)]
        if not game_teams:
            continue
        pid = pl.original_id if pl.is_original else player_ids[pl.uid]
        own = teams_of.get(pid, set()) if pl.is_original else set()
        for lk in game_teams:
            if lk.team not in own:
                position = lk.position
                if position is None:
                    position = first_position.get(pl.ref)
                    if position is None and pl.is_original and game_links.get(pid) is not None:
                        position = db.get(links, game_links[pid], 'position')
                    position = BENCH_POSITION if position is None else position
                squads.setdefault(lk.team, (set(), {}, []))[2].append((pid, lk.number, position))
                first_position.setdefault(pl.ref, position)
    for tid, (leave, update, join) in squads.items():
        if leave or join:
            say(f'team {tid}: {len(leave)} leave, {len(join)} join')
        _game_team_squad(db, tid, leave, update, join, None)

    # ---- original teams edited in place (same teamid): only what changed since they were loaded
    for k, tm in enumerate(project.original_teams):
        step('teams', len(project.new_teams) + k, len(project.teams))
        league_id = league_ids.get(tm.league) if isinstance(tm.league, str) else int(tm.league)
        if league_id is None or league_id not in existing:
            raise BuildError(f'{tm.name}: league {tm.league} does not exist', tm.uid)
        for job in _build_original_team(db, game, tm, assets_dir, league_id, texts, say, player_ids):
            future = pool.submit(job)
            jobs.append(future)
            original_jobs.add(future)
    step('teams', len(project.teams), len(project.teams))
    try:
        for k, job in enumerate(jobs):
            step('images', k, len(jobs))
            files, lines = job.result()
            for name, data in files.items():
                archive = _archive_of(game, name) if job in original_jobs else None
                if archive:  # a file the game has: replaced inside its archive (a loose file would lose)
                    entries[archive, name] = data
                else:
                    result.loose[name] = data
            for line in lines:
                say('  ' + line)
    finally:
        pool.shutdown(cancel_futures=True)
    step('images', len(jobs), len(jobs))

    apply_original_changes(db, project.originals)
    out = db.db.build()
    bad = dbcrc.check(out)
    if bad:
        raise BuildError(f'invalid database CRC (bug): {bad[:5]}')
    t3db.Database(out, game.meta)  # must parse back
    # same texts in every language of every locale file (same keys; pt-BR file read when the game runs in pt-BR)
    for file in LOCALE_FILES:
        for entry in LOCALE_ENTRIES:
            step('texts', len(entries), len(LOCALE_FILES) * len(LOCALE_ENTRIES))
            data = locale_data if (file, entry) == (LOCALE_FILES[0], LOCALE_ENTRY) else game.locale(file, entry)[1]
            try:
                new_locale = locale.set_strings(texts, data) if texts else data
            except (locale.LocaleError, ValueError) as e:
                raise BuildError(f'{os.path.basename(file)} {entry}: {e}') from e
            entries[os.path.basename(file), entry] = new_locale
    step('texts', len(entries), len(entries))
    try:
        entries.update(gamepatches.entries(game, project.game_patches))
    except gamepatches.GamePatchError as e:
        raise BuildError(str(e)) from e
    say(f'database {len(out)} bytes; {len(texts)} texts; {len(entries)} replaced entries')
    result.database = out
    result.entries = entries
    return result


BUILD_STATE = '.fsmod_build.json'  # inside the patch folder: what the reused archives contain


def write_patch(result, game, out_dir, progress=None):
    """Writes the patch into out_dir, mirroring the game root (copy each folder over the game's folder):

      Game/data8.big, Game/data8.bh            database (the game reads d:\\data8.big over data0)
      Game/<path of every PATCH_TARGETS file>   whole archive: the original with the new entries, or the plain
                                                original when the project changes nothing in it
                                                (data0.big, data1.big, data3.big, data7.big, data/loc/locale*.big,
                                                .../2dheads.big; data0 only changes with fsmod.gamepatches)
      Game/<its .bh>                            always, for the archives that have one (dataN.bh, 2dheads.bh)
      Game/<internal name>                      loose files (result.loose): the game opens d:/<name> from disk
                                                when no archive has it (validated with a country flag, 20/10)

    An entry that fits its original space is written in place (zero padded; the index keeps the original size).
    A bigger one is appended at the end of the archive (aligned to 0x40) and its offset/size are updated in the
    BIG4 header and in the .bh, like ReStreet's installer does for data1.big (validated in game).
    Archives are reused between builds (BUILD_STATE): the ranges written last time and the header are restored
    from the original and the appended tail is cut, so data3.big (1.1 GB) and data7.big are not copied
    on every build.
    Anything else in out_dir is removed.
    Every target always goes, changed or not: copying Game/ over any earlier install (or over a mod built before)
    then always leaves the game exactly as this project says (decision of the user, 21/10/2026).
    progress(step, done, total): step 'files' (the archives one by one, then the database and the loose files).
    """
    import json
    import shutil
    import struct
    by_file = {}
    for (short, name), data in result.entries.items():
        if short not in PATCH_TARGETS:
            raise BuildError(f'unknown archive {short} (bug)')
        by_file.setdefault(short, {})[name] = data

    state_path = os.path.join(out_dir, BUILD_STATE)
    previous = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding='utf-8') as f:
                previous = json.load(f).get('files', {})
        except (OSError, ValueError):
            previous = {}
        os.remove(state_path)  # rewritten only when everything below succeeds

    game_out = os.path.join(out_dir, GAME_DATA)
    os.makedirs(game_out, exist_ok=True)
    for entry in os.listdir(out_dir):  # old layouts (GameData/, Mods/) and stray files
        if entry != GAME_DATA:
            path = os.path.join(out_dir, entry)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    step = progress or (lambda *_: None)
    files_total = len(PATCH_TARGETS) + 1
    written, state = set(), {}
    for k, short in enumerate(sorted(PATCH_TARGETS)):
        step('files', k, files_total)
        items = by_file.get(short, {})
        src, dst = game.target_path(short), os.path.join(game_out, PATCH_TARGETS[short])
        toc, hdr_len = big.read_toc_positions(src)
        st = os.stat(src)
        source = [st.st_size, st.st_mtime_ns]
        prev = previous.get(short)
        reuse = bool(prev) and prev.get('source') == source and os.path.exists(dst) and \
            os.path.getsize(dst) >= st.st_size
        if not reuse:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        ranges, moved = [], {}
        with open(dst, 'r+b') as out, open(src, 'rb') as orig:
            if reuse:
                out.truncate(st.st_size)
                for offset, length in prev['ranges'] + [[0, hdr_len]]:
                    orig.seek(offset)
                    out.seek(offset)
                    out.write(orig.read(length))
            end = st.st_size
            for name, data in sorted(items.items()):
                if name not in toc:
                    raise BuildError(f'{name} is not in {short} (bug)')
                pos, offset, size = toc[name]
                if len(data) <= size:
                    out.seek(offset)
                    out.write(data + bytes(size - len(data)))
                    ranges.append([offset, size])
                    continue
                new_offset = end + (-end % big.ALIGN)
                out.seek(end)
                out.write(bytes(new_offset - end) + data)
                end = new_offset + len(data)
                out.seek(pos)
                out.write(struct.pack('>II', new_offset, len(data)))
                moved[name] = (offset, size, new_offset, len(data))
            if moved:
                out.seek(4)
                out.write(struct.pack('<I', end))
        written.add(os.path.normcase(dst))

        index = game.index_path(short)
        if index:
            bh = bytearray(open(index, 'rb').read())
            slots = {}
            for i in range(struct.unpack('>I', bh[8:12])[0]):
                off, size, _, _, h = struct.unpack('>IIIII', bh[16 + 20 * i:36 + 20 * i])
                slots.setdefault((off, size, h), []).append(16 + 20 * i)
            for name, (offset, size, new_offset, new_size) in moved.items():
                hits = slots.get((offset, size, big.djb2(name.encode())), [])
                if len(hits) != 1:
                    raise BuildError(f'{name}: not found once in {os.path.basename(index)} (bug)')
                struct.pack_into('>II', bh, hits[0], new_offset, new_size)
            bh_dst = dst[:-4] + '.bh'
            with open(bh_dst, 'wb') as f:
                f.write(bh)
            written.add(os.path.normcase(bh_dst))
        state[short] = {'source': source, 'ranges': ranges, 'moved': sorted(moved)}

    step('files', len(PATCH_TARGETS), files_total)
    big_data, bh_data = big.build_patch([(DB_ENTRY, result.database)], game.db_bh_unknown)
    for name, data in (('data8.big', big_data), ('data8.bh', bh_data)):
        with open(os.path.join(game_out, name), 'wb') as f:
            f.write(data)
        written.add(os.path.normcase(os.path.join(game_out, name)))
    for name, data in result.loose.items():
        path = os.path.join(game_out, *name.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        written.add(os.path.normcase(path))
    for root, dirs, files in os.walk(game_out, topdown=False):  # files of earlier builds, empty folders
        for n in files:
            if os.path.normcase(os.path.join(root, n)) not in written:
                os.remove(os.path.join(root, n))
        for d in dirs:
            path = os.path.join(root, d)
            if not os.listdir(path):
                os.rmdir(path)
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump({'files': state}, f, indent=2)
    step('files', files_total, files_total)
    return out_dir
