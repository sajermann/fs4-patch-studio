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
  - Original leagues edited in place (League.original_id): texts, selector order and the flags of their country
    (original_league); original teams without a league go to HIDDEN_TEAMS_LEAGUE.
  - New players: cloned from generic players (headclasscode 1), new nameids and a playerid the game does not
    use anywhere (Player.player_id, given once by the build). Photo and real face (headclasscode 0, files named
    by the playerid) are loose files: the game opens d:/<name> from disk when no archive has it.

Output: database bytes (goes into data8.big/.bh) + new entries {(archive, entry name): bytes} that replace
entries of original game archives. write_patch() writes them in the layout of PATCH_LAYOUT: since 10/11/2026 each
replaced entry is a loose file with its record zeroed in the archive's .bh (write_patch_loose); until then the whole
patched archives went (write_patch_archives, still there to go back).
"""
import datetime
import io
import os
import re
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from PIL import Image

from . import (balls, big, body, boots, buildcache, chunk, crest, dbcrc, facework, gamepatches, gloves, kit,
               kitfonts, leaguelogo, locale, model, original_league, original_player, original_team, photo, preview,
               rx3tex, scanface, t3db, workers, world_tour)
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
NO_BIRTHDATE = 0  # players.birthdate of a player with no birth date (the column's day 0; tested in game)


def _birth_days(birthdate):
    """players.birthdate of a Player.birthdate (YYYY-MM-DD, or None = no birth date)."""
    return (datetime.date.fromisoformat(birthdate) - EPOCH).days if birthdate else NO_BIRTHDATE
MAX_ROSTER = 13
MIN_ROSTER = 6  # the smallest roster of the game's own teams; with far fewer the game starts but a match crashes
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
GOALKEEPER = gloves.GOALKEEPER  # teamplayerlinks.position of the goalkeeper


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
    assigned_boot_codes: dict = field(default_factory=dict)  # {boot uid: code} given during this build
    assigned_glove_codes: dict = field(default_factory=dict)  # {glove uid: code} given during this build
    assigned_ball_codes: dict = field(default_factory=dict)  # {ball uid: id} given during this build
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

    @staticmethod
    def put_any(table, row, field_name, value):
        """Like put, for floats too."""
        f = table.field(field_name)
        if f.type == 4:
            row[table.fields.index(f)] = struct.unpack('>I', struct.pack('>f', value))[0]
        else:
            Db.put(table, row, field_name, value)

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
    used = set(reserved) | {lg.league_id for lg in project.new_leagues if lg.league_id is not None}
    out, lid = {}, FIRST_NEW_LEAGUEID
    for lg in project.new_leagues:
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


def assign_boot_codes(project, game):
    """{boot uid: code} for the new boots of the project whose code is missing or no longer fits (a street boot needs
    a free street code, any other one a free code from boots.NEW_CODES; no two boots share one). Codes stay with the
    boot once written back. Raises BuildError when a street boot finds no free street code."""
    pools = {True: boots.free_street_codes(game), False: boots.free_new_codes(game)}
    news = [b for b in project.boots if not b.is_original]
    keep, used = set(), set()
    for b in news:  # the first boot with a fitting code keeps it
        if b.code in pools[b.street] and b.code not in used:
            used.add(b.code)
            keep.add(b.uid)
    out = {}
    for b in news:
        if b.uid in keep:
            continue
        code = next((c for c in pools[b.street] if c not in used), None)
        if code is None:
            raise BuildError(f'{b.name}: no free {"street " if b.street else ""}boot code left', b.uid)
        used.add(code)
        out[b.uid] = code
    return out


def assign_glove_codes(project, game):
    """{glove uid: code} for the new gloves of the project whose code is missing or no longer free (gloves.free_codes;
    no two gloves share one). Codes stay with the glove once written back. Raises BuildError when no code is left."""
    pool = gloves.free_codes(game)
    news = [g for g in project.gloves if not g.is_original]
    keep, used = set(), set()
    for g in news:  # the first glove with a fitting code keeps it
        if g.code in pool and g.code not in used:
            used.add(g.code)
            keep.add(g.uid)
    out = {}
    for g in news:
        if g.uid in keep:
            continue
        code = next((c for c in pool if c not in used), None)
        if code is None:
            raise BuildError(f'{g.name}: no free glove code left ({len(pool)} in all)', g.uid)
        used.add(code)
        out[g.uid] = code
    return out


def _kit_files(game, tid, kind_n, colors, crest_img):
    """(files, log lines) of one kit of a new team (runs in the image pool)."""
    lines = []
    files = kit.build(game, tid, kind_n, colors['jersey'], colors['shorts'], crest_img, erase_original_badge=True,
                      log=lines.append)
    return files, lines


def _real_kit_files(game, tid, kind_n, real, assets_dir, crest_img, uid, cache=None):
    """(files, log lines) of one real kit (fsmod.kit.build_real; runs in the image pool). cache: a
    buildcache.BuildCache (files reused when the images, the ids and the app are the same)."""
    lines = []
    sources = {}
    for part in model.REAL_KIT_FILES:
        path = getattr(real, part)
        if path:
            try:
                sources[part] = buildcache.file_bytes(os.path.join(assets_dir, path))
            except OSError as e:
                raise BuildError(f'cannot read kit image {path}: {e}', uid) from e
    k = None
    if cache is not None:
        crest_part = [] if 'thumbnail' in sources or crest_img is None else [crest_img.size, crest_img.tobytes()]
        k = buildcache.key('real_kit', cache.game_key, tid, kind_n, *(
            x for part in sorted(sources) for x in (part, sources[part])), *crest_part,
            repr((real.positions, real.show_name)))
        files = cache.get(k)
        if files is not None:
            return files, [f'{kit.kit_name(tid, kind_n)}: reused (cache)']
    images = {}
    for part, data in sources.items():
        try:
            images[part] = Image.open(io.BytesIO(data))
            images[part].load()
        except OSError as e:
            raise BuildError(f'cannot read kit image {getattr(real, part)}: {e}', uid) from e
    files = kit.build_real(game, tid, kind_n, images['jersey'], images['shorts'], images.get('thumbnail'), crest_img,
                           log=lines.append, positions=real.positions, show_name=real.show_name)
    if k is not None:
        cache.put(k, files)
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
        # the game picks one of the slots for each player in each match: a shorter list repeats (one piece fixes it)
        for n in range(STREET_SLOTS[col]):
            slot = piece.pieces[n % len(piece.pieces)]
            db.put(table, row, f'{col}_geo_type_{n + 1}', slot.style)
            db.put(table, row, f'{col}_texture_pattern_{n + 1}', slot.pattern)
        for which, c in zip(('primary', 'secondary', 'tertiary'), piece.colors):
            for ch, v in zip('rgb', c):
                db.put(table, row, f'{col}_color_{which}_{ch}', v)


class _KitFonts:
    """The real kits' own fonts (fsmod.kitfonts): a free font number for each different file in use, its files as
    loose files (result.loose), and the number each kit's font field gets (value)."""

    def __init__(self, project, game, assets_dir, result, say):
        self.assets_dir = assets_dir
        self.game = game
        self._digests = {}
        kits = [real for tm in project.teams if tm.use_real_kits
                for real in (tm.real_kit(slot) for slot in ('home', 'away', 'goalkeeper')) if real]
        self.ids = kitfonts.assign_font_ids(kits, self.read)
        left = sum(v is None for v in self.ids.values())
        if left:
            say(f'real kit fonts: {left} without a free font number, a game font is used instead')
        written = set()
        for real in kits:
            for field, file_field in kitfonts.FONT_PARTS:
                font = self.value(real, field) if getattr(real, field) == kitfonts.KIT else None
                if font is None:
                    continue
                data = self.read(getattr(real, file_field))
                if field == 'name_font':
                    name = kitfonts.NAME_FILE.format(font)
                    if name not in written:
                        result.loose[name] = chunk.chunkzip(kitfonts.name_file(data))
                        say(f'name font {font}: {real.name_font_name or getattr(real, file_field)}')
                    written.add(name)
                    continue
                color = real.number_color if field == 'number_font' else real.shorts_number_color
                name = kitfonts.NUMBERS_FILE.format(font, color)
                if name not in written:
                    try:
                        result.loose[name] = chunk.chunkzip(kitfonts.number_file(game, data, font, color))
                    except (kitfonts.FontError, ValueError) as e:
                        raise BuildError(f'{getattr(real, file_field)}: not a kit numbers file ({e})') from e
                    say(f'number font {font} (color {color})')
                written.add(name)

    def read(self, path):
        try:
            with open(os.path.join(self.assets_dir, path), 'rb') as f:
                return f.read()
        except OSError as e:
            raise BuildError(f'cannot read the kit font {path}: {e}') from e

    def has_own(self, font, color):
        """A kit's own numbers file got font number `font` in `color` (written as a loose file)."""
        return any(key[0] == 'number' and key[2] == color and n == font for key, n in self.ids.items())

    def value(self, real, field):
        """Font number the teamkits field gets for a RealKit font field, None = keep the row's."""
        v = getattr(real, field)
        if v != kitfonts.KIT:
            return v
        path = getattr(real, dict(kitfonts.FONT_PARTS)[field])
        if not path:
            return None
        if path not in self._digests:
            self._digests[path] = kitfonts.digest(self.read(path))
        return self.ids.get(kitfonts.font_key(real, field, self._digests[path]))


def _real_kit_fields(db, table, row, real, fonts=None):
    """teamkits fields of a real kit: name/number colors, collar, front number, fonts and name layout."""
    for ch, v in zip('rgb', real.name_color):
        db.put(table, row, f'jerseynamecolor{ch}', v)
    db.put(table, row, 'numbercolor', real.number_color)
    db.put(table, row, 'shortsnumbercolor', real.shorts_number_color)
    db.put(table, row, 'jerseycollargeometrytype', real.collar)
    db.put(table, row, 'jerseyfrontnumberplacementcode', 1 if real.front_number else 0)
    if real.shorts_number is not None:
        db.put(table, row, 'shortsnumberplacementcode', 1 if real.shorts_number else 0)
    for name, field in (('name_font', 'jerseynamefonttype'), ('number_font', 'numberfonttype'),
                        ('shorts_number_font', 'shortsnumberfonttype'), ('name_layout', 'jerseynamelayouttype')):
        value = fonts.value(real, name) if fonts and name != 'name_layout' else getattr(real, name)
        if value is not None and value != kitfonts.KIT:
            db.put(table, row, field, value)
    if fonts:  # the numbers must always show: a font without the kit's color (no file) would be a broken texture
        for field, color in (('numberfonttype', real.number_color), ('shortsnumberfonttype', real.shorts_number_color)):
            font = db.get(table, row, field)
            if not (kit.number_font_ok(fonts.game, font, color) or fonts.has_own(font, color)):
                db.put(table, row, field, kitfonts.FALLBACK_NUMBER_FONT)


def set_piece_fallback(captain, squad, positions):
    """Who takes a set piece nobody was given: the captain, unless he is the goalkeeper (a goalkeeper takes one only
    when chosen); then the first outfield player of squad (playerids in order; positions: playerid -> position), else
    the captain."""
    if positions.get(captain) != GOALKEEPER:
        return captain
    return next((pid for pid in squad if positions.get(pid) not in (None, GOALKEEPER)), captain)


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
    squad_rows = [links.records[k] for k in db.rows('teamplayerlinks', 'teamid', tid)]
    squad = [db.get(links, r, 'playerid') for r in squad_rows]
    positions = {db.get(links, r, 'playerid'): db.get(links, r, 'position') for r in squad_rows}
    heir = join[0][0] if join else (squad[0] if squad else None)
    # set pieces: the heir unless he is the goalkeeper (then the first outfield player who joined, else of the squad)
    outfield = [pid for pid, _, _ in join] + squad
    taker_heir = set_piece_fallback(heir, outfield, positions)
    for f in TAKER_FIELDS:
        if db.get(teams, team_row, f) in leave and heir is not None:
            db.put(teams, team_row, f, heir if f == 'captainid' else taker_heir)


def _team_league_ids(tm, league_ids, existing):
    """The leagueids of a team's leagues (a new league by uid: the id this build gave it)."""
    out = []
    for lg in tm.leagues:
        lid = league_ids.get(lg) if isinstance(lg, str) else int(lg)
        if lid is None or lid not in existing:
            raise BuildError(f'{tm.name}: league {lg} does not exist', tm.uid)
        out.append(lid)
    return out


def _set_team_leagues(db, tid, lids, model):
    """Replaces the leagueteamlinks rows of team tid by one per leagueid in lids, each last in its league (a team in
    several leagues shows in each one, validated in game: test LT1). model = (row, raw) the rows are copied from."""
    t = db.table('leagueteamlinks')
    for k in sorted(db.rows('leagueteamlinks', 'teamid', tid), reverse=True):
        del t.records[k]
        del t.raw_records[k]
    for lid in lids:
        r = list(model[0])
        db.put(t, r, 'teamid', tid)
        db.put(t, r, 'leagueid', lid)
        db.put(t, r, 'tableposition', len(db.rows('leagueteamlinks', 'leagueid', lid)) + 1)
        db.put(t, r, 'artificialkey', db.max_value('leagueteamlinks', 'artificialkey') + 1)
        db.append('leagueteamlinks', r, model[1])


def _build_original_league(db, game, lg, assets_dir, texts, entries, result, say):
    """Applies an original league entry (League.original_id) to the game's own record, texts and flags, only where it
    differs from what was loaded (original_league.changes). A changed image replaces the flag of the league's
    country where the game has it (data1), otherwise it goes as a loose file (fsmod.leaguelogo)."""
    lid = lg.original_id
    ch = original_league.changes(lg, assets_dir)
    leagues = db.table('leagues')
    rows = db.rows('leagues', 'leagueid', lid)
    if not rows:
        raise BuildError(f'{lg.name}: original league {lid} does not exist', lg.uid)
    row = leagues.records[rows[0]]
    say(f'original league {lid} "{lg.name}"' + ('' if ch.any else ' (unchanged)'))
    if 'name' in ch.texts:
        texts[f'LeagueName_{lid}'] = lg.name
    if 'short_name' in ch.texts:
        texts[f'LeagueName_Abbr15_{lid}'] = lg.short_name or lg.name
    if ch.sort_order:
        db.put(leagues, row, 'defaultsortorder', lg.sort_order)
    square_path = lg.image or lg.wide_image
    if ch.images and square_path:
        img = Image.open(os.path.join(assets_dir, square_path)).convert('RGBA')
        wide = Image.open(os.path.join(assets_dir, lg.wide_image)).convert('RGBA') if lg.wide_image else None
        country = db.get(leagues, row, 'countryid')
        changed = {leaguelogo.asset_name(asset, country) for attr, asset in original_league.IMAGES if attr in ch.images}
        for name, data in leaguelogo.flag_files(game, country, img, wide, lg.wide_image_fit).items():
            if name not in changed:
                continue
            loc = game.locate(name)
            if loc:
                entries[f'data{loc[0]}.big', name] = data
            else:
                result.loose[name] = data


def _build_original_team(db, game, tm, assets_dir, lids, texts, say, player_ids, cache=None, fonts=None):
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
    if ch.league:  # no league: hidden in the game (the league that holds hidden teams), like a hidden team
        league_links = db.table('leagueteamlinks')
        k = db.rows('leagueteamlinks', 'teamid', tid)[0]
        _set_team_leagues(db, tid, lids or [HIDDEN_TEAMS_LEAGUE], (league_links.records[k], league_links.raw_records[k]))

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
                _real_kit_fields(db, team_kits, kit_rows[n], real, fonts)
            if 'jersey' in parts or ch.kits_mode:
                # a new jersey is a real kit of its own (crest painted in, FIFA 16 positions): built like a new team's
                thumb = real.thumbnail if 'thumbnail' in parts else None
                jobs.append(lambda n=n, real=real, thumb=thumb: _real_kit_files(
                    game, tid, n, real.model_copy(update={'thumbnail': thumb}), assets_dir, crest_image(), tm.uid,
                    cache))
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


def _fit_body_type(db, players, row):
    """The row's body type in the height class of its height, keeping the build (fsmod.body): the user picks the
    build, the height (own or inherited from the template player) picks the class."""
    code = db.get(players, row, 'bodytypecode')
    fitted = body.fit(code, db.get(players, row, 'height'))
    if fitted != code:
        db.put(players, row, 'bodytypecode', fitted)


def _build_original_player(db, game, pl, assets_dir, nameid, faces, say):
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
        if 'birthdate' in f:  # cleared = no birth date (day 0)
            db.put(players, row, 'birthdate', _birth_days(pl.birthdate))
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
        body_changed = pl.appearance.get('bodytypecode') != before.get('appearance', {}).get('bodytypecode')
        if 'height' in f or body_changed:
            _fit_body_type(db, players, row)  # the game's own combinations stay as they are until one of the two changes
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
        task = faces.submit(pl, pid, db.get(players, row, 'haircolorcode'))
        jobs.append(task.result)
    return jobs


def _edited_kit_files(game, tid, kind_n, shorts_path, crest_img):
    """The game's own kit rx3 of an original team with new shorts and/or a new crest decal."""
    name = kit.kit_name(tid, kind_n)
    d = bytearray(chunk.decode(game.read_entry(name)[2]))
    if shorts_path:
        d = kit.set_real_texture(d, 'shorts_cm', Image.open(shorts_path).convert('RGB'))
    if crest_img is not None:
        d = crest.set_texture(d, crest_img)
    return {name: chunk.chunkzip(bytes(d))}, [f'{name}: edited']


class _FaceTask:
    """One real face being converted: result() = ({loose file name: bytes}, log lines)."""

    def __init__(self, pl, task=None, files=None, cache=None, key=None):
        self.pl, self.task, self.files, self.cache, self.key = pl, task, files, cache, key
        self.lines = [f'face of {pl.shown_name}: reused (cache)'] if files is not None else []

    def result(self):
        if self.files is None:
            try:
                self.files = self.task.result()
            except (ValueError, KeyError) as e:
                raise BuildError(f'{self.pl.shown_name}: face {self.pl.face.source_id}: {e}', self.pl.uid) from e
            if self.cache is not None:
                self.cache.put(self.key, self.files)
        return self.files, self.lines


class _Faces:
    """Converts the real faces of a build in worker processes (fsmod.workers, fsmod.facework): the conversion is
    pure Python, so threads would run one at a time. A face already converted with the same inputs comes from the
    cache. The pool starts with the first face that is not in the cache."""

    def __init__(self, game, assets_dir, workers, cache, say):
        self.game, self.assets_dir, self.workers, self.cache, self.say = game, assets_dir, workers, cache, say
        self.pool = None

    def submit(self, pl, pid, hair_color_code):
        try:
            files = scanface.read_files(scanface.project_face_dir(self.assets_dir, pl.uid), pl.face.source_id)
        except (ValueError, KeyError, OSError) as e:
            raise BuildError(f'{pl.shown_name}: face {pl.face.source_id}: {e}', pl.uid) from e
        options = (pid, preview.hair_color(hair_color_code), pl.face.paint_scalp, pl.face.hair_mode,
                   pl.face.hair_thickness)
        k = None
        if self.cache is not None:
            k = buildcache.key('face', self.cache.game_key, *options, *(
                x for name in sorted(files) for x in (name, files[name])))
            cached = self.cache.get(k)
            if cached is not None:
                return _FaceTask(pl, files=cached, key=k)
        if self.pool is None:
            self.pool = workers.Pool(self.workers, facework.init, (scanface.template_files(self.game),),
                                     log_fn=self.say, local_initializer=facework.init_here)
        return _FaceTask(pl, self.pool.submit(facework.convert, files, *options), cache=self.cache, key=k)

    def close(self):
        if self.pool is not None:
            self.pool.shutdown()


def _rgb(value, what, entity):
    if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(0 <= int(x) <= 255 for x in value)):
        raise BuildError(f'{what}: invalid color {value!r} (use [R, G, B])', entity)
    return tuple(int(x) for x in value)


# ---------------------------------------------------------------- build
def _read_boot(assets_dir, boot):
    try:
        with open(os.path.join(assets_dir, boot.mesh), 'rb') as f:
            mesh = f.read()
        with open(os.path.join(assets_dir, boot.texture), 'rb') as f:
            texture = f.read()
    except OSError as e:
        raise BuildError(f'{boot.name}: cannot read the boot files: {e}', boot.uid) from e
    return mesh, texture


def _build_boots(db, game, project, assets_dir, player_ids, entries, result, say, converter=None):
    """New boots worn by a player get a code (assign_boot_codes) and loose files; edited game boots with files of
    their own replace the game's inside its archive; each player's boot columns point to his boots. Runs before the
    World Tour (its clones copy the player rows)."""
    news = {b.uid: b for b in project.boots if not b.is_original}
    edited = [b for b in project.boots if b.is_original and b.has_files]
    worn = {uid for pl in project.players for uid in pl.boots.values() if uid in news and news[uid].has_files}
    if not worn and not edited:
        return
    converter = converter or boots.Converter(game)
    result.assigned_boot_codes = assign_boot_codes(project, game)
    codes = {uid: result.assigned_boot_codes.get(uid, b.code) for uid, b in news.items()}

    def convert(boot, code):
        try:
            return converter.files(*_read_boot(assets_dir, boot), code)
        except boots.BootError as e:
            raise BuildError(f'{boot.name}: {e}', boot.uid) from e

    for b in edited:
        say(f'boot {b.original_id} (game boot) "{b.name}": files replaced')
        for name, data in convert(b, b.original_id).items():
            entries[_archive_of(game, name), name] = chunk.chunkzip(data)
    for uid in sorted(worn, key=lambda u: codes[u]):
        say(f'boot {codes[uid]} "{news[uid].name}"')
        for name, data in convert(news[uid], codes[uid]).items():
            result.loose[name] = chunk.chunkzip(data)
    players = db.table('players')
    for pl in project.players:
        mine = {s: codes[uid] for s, uid in pl.boots.items() if uid in worn}
        if not mine:
            continue
        pid = pl.original_id if pl.is_original else player_ids.get(pl.uid)
        rows = db.rows('players', 'playerid', pid) if pid is not None else []
        for k in rows:
            for surface, code in mine.items():
                db.put(players, players.records[k], boots.SURFACE_FIELDS[surface], code)


def assign_ball_codes(project, game):
    """{ball uid: id} for the new balls of the project whose id is missing or no longer free (balls.free_ids; no two
    balls share one). Ids stay with the ball once written back. Raises BuildError when no id is left."""
    pool = balls.free_ids(game)
    news = [b for b in project.balls if not b.is_original]
    keep, used = set(), set()
    for b in news:  # the first ball with a fitting id keeps it
        if b.code in pool and b.code not in used:
            used.add(b.code)
            keep.add(b.uid)
    out = {}
    for b in news:
        if b.uid in keep:
            continue
        code = next((c for c in pool if c not in used), None)
        if code is None:
            raise BuildError(f'{b.name}: no free ball id left ({len(pool)} in all)', b.uid)
        used.add(code)
        out[b.uid] = code
    return out


def _build_balls(db, game, project, assets_dir, entries, result, say, converter=None):
    """New balls some stadium uses get an id (assign_ball_codes) and loose files (inside data8 the game does not find
    them); edited game balls with files of their own replace the game's inside its archive; each stadium row the user
    gave a ball (originals.stadium_balls) gets its id. A stadium whose ball is hidden or unknown keeps the game's."""
    news = {b.uid: b for b in project.balls if not b.is_original}
    edited = [b for b in project.balls if b.is_original and b.has_files]
    picked = project.originals.stadium_balls
    if not news and not edited and not picked:
        return
    used = {ref for ref in picked.values() if ref in news and news[ref].has_files}
    converter = converter or balls.Converter(game)
    result.assigned_ball_codes = assign_ball_codes(project, game)
    codes = {uid: result.assigned_ball_codes.get(uid, b.code) for uid, b in news.items()}

    def convert(ball, ball_id):
        data = []
        for f in model.BALL_FILES:
            try:
                with open(os.path.join(assets_dir, getattr(ball, f)), 'rb') as fh:
                    data.append(fh.read())
            except OSError as e:
                raise BuildError(f'{ball.name}: cannot read the ball file: {e}', ball.uid) from e
        try:
            return converter.files(*data, ball_id)
        except balls.BallError as e:
            raise BuildError(f'{ball.name}: {e}', ball.uid) from e

    for b in edited:
        say(f'ball {b.original_id} (game ball) "{b.name}": files replaced')
        for name, data in convert(b, b.original_id).items():
            entries[_archive_of(game, name), name] = chunk.chunkzip(data)
    for uid in sorted(used, key=lambda u: codes[u]):
        say(f'ball {codes[uid]} "{news[uid].name}"')
        for name, data in convert(news[uid], codes[uid]).items():
            result.loose[name] = chunk.chunkzip(data)
    game_ids = set(balls.game_ids(game))
    stadiums = db.table('stadiums')
    for sid, ref in sorted(picked.items()):
        ball_id = codes[ref] if ref in used else ref if isinstance(ref, int) and ref in game_ids else None
        if ball_id is None:
            continue  # a hidden (or file-less) ball: the stadium keeps the game's
        rows = db.rows('stadiums', 'stadiumid', sid)
        if not rows:
            raise BuildError(f'stadium {sid} not found')
        for k in rows:
            db.put(stadiums, stadiums.records[k], balls.FIELD, ball_id)


def _build_gloves(db, game, project, assets_dir, player_ids, entries, result, say, converter=None):
    """New gloves worn by a player get a code (assign_glove_codes) and loose files (inside data8 the game shows them
    broken); edited game gloves with a file of their own replace the game's inside its archive; each player who picked
    a glove gets its code. Runs before the World Tour (its clones copy the player rows)."""
    news = {g.uid: g for g in project.gloves if not g.is_original}
    edited = [g for g in project.gloves if g.is_original and g.has_files]
    picked = [pl for pl in project.players if pl.glove is not None]
    if not news and not edited and not picked:
        return
    worn = {pl.glove for pl in picked if pl.glove in news and news[pl.glove].has_files}
    converter = converter or gloves.Converter(game)
    result.assigned_glove_codes = assign_glove_codes(project, game)
    codes = {uid: result.assigned_glove_codes.get(uid, g.code) for uid, g in news.items()}

    def convert(glove, code):
        try:
            with open(os.path.join(assets_dir, glove.texture), 'rb') as f:
                texture = f.read()
        except OSError as e:
            raise BuildError(f'{glove.name}: cannot read the glove file: {e}', glove.uid) from e
        try:
            return converter.files(texture, code)
        except gloves.GloveError as e:
            raise BuildError(f'{glove.name}: {e}', glove.uid) from e

    for g in edited:
        say(f'glove {g.original_id} (game glove) "{g.name}": files replaced')
        for name, data in convert(g, g.original_id).items():
            entries[_archive_of(game, name), name] = chunk.chunkzip(data)
    for uid in sorted(worn, key=lambda u: codes[u]):
        say(f'glove {codes[uid]} "{news[uid].name}"')
        for name, data in convert(news[uid], codes[uid]).items():
            result.loose[name] = chunk.chunkzip(data)
    game_codes = set(gloves.game_codes(game))
    players = db.table('players')
    for pl in picked:
        code = codes[pl.glove] if pl.glove in worn else pl.glove if isinstance(pl.glove, int) else None
        if code is None or (isinstance(pl.glove, int) and code not in game_codes):
            continue  # a hidden (or file-less) glove: he keeps his code
        pid = pl.original_id if pl.is_original else player_ids.get(pl.uid)
        for k in (db.rows('players', 'playerid', pid) if pid is not None else []):
            db.put(players, players.records[k], gloves.FIELD, code)


def _set_preferred_positions(db, game, project, player_ids, result, say):
    """players.preferredposition1 of every project player by the app's rule (gloves.preferred_position): goalkeeper
    with a picked glove, else his most common team position. An original player keeps the game's unless the rule
    makes him a goalkeeper or takes him out of goal. A goalkeeper whose gkglovetypecode has no glove files (most
    often 0, from the template row, when no glove was picked) gets the game's default glove: the game would load
    gkglove_0_0_cm, which does not exist, and show a broken texture."""
    players = db.table('players')
    with_files = set(gloves.game_codes(game)) | set(result.assigned_glove_codes.values())
    for pl in project.players:
        pid = pl.original_id if pl.is_original else player_ids.get(pl.uid)
        for k in (db.rows('players', 'playerid', pid) if pid is not None else []):
            row = players.records[k]
            current = db.get(players, row, 'preferredposition1')
            position = gloves.preferred_position(pl, current if pl.is_original else None)
            if current != position:
                db.put(players, row, 'preferredposition1', position)
                if pl.is_original:
                    say(f'original player {pid} "{pl.shown_name}": preferred position {position}')
            code = db.get(players, row, gloves.FIELD)
            if position == gloves.GOALKEEPER and code not in with_files:
                db.put(players, row, gloves.FIELD, gloves.DEFAULT_CODE)
                say(f'player {pid} "{pl.shown_name}": goalkeeper without glove files ({code}), default glove '
                    f'{gloves.DEFAULT_CODE}')


def build(project, game, assets_dir, log=None, progress=None, boot_converter=None, glove_converter=None,
          ball_converter=None, worker_count=None, cache=None):
    """Builds the mod. assets_dir = folder that image paths (crests) are relative to. Hidden leagues/teams are
    left out (Project.visible); their ids stay reserved. progress(step, done, total) is called as the build goes
    (steps: BUILD_STEPS, then write_patch's). boot_converter / glove_converter / ball_converter: a boots.Converter /
    gloves.Converter / balls.Converter to reuse (keeps its conversions). worker_count: threads for the image files and
    processes for the real faces (None = fsmod.workers.plan(), the machine's defaults). cache: a
    buildcache.BuildCache whose folder keeps the real faces and kits between builds (None = no cache); entries this
    build did not use are deleted at the end."""
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
    fonts = _KitFonts(project, game, assets_dir, result, say)  # the real kits' own fonts
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
    result.assigned_league_ids = assign_league_ids(
        project, reserved_leagues | {lg.league_id for lg in every.new_leagues})
    league_ids = {}
    if len(project.new_leagues) > len(IMAGE_COUNTRIES):
        raise BuildError(f'{len(project.new_leagues)} new leagues: at most {len(IMAGE_COUNTRIES)} (one image each)')
    for k, lg in enumerate(project.new_leagues):
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
    hidden_originals = set(every.originals.hidden_leagues)
    for k, lg in enumerate(project.original_leagues):
        step('leagues', len(project.new_leagues) + k, len(project.leagues))
        if lg.original_id not in hidden_originals:  # a hidden one leaves the selector: nothing to edit
            _build_original_league(db, game, lg, assets_dir, texts, entries, result, say)

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
    built_pids = set()
    worker_count = workers.plan() if worker_count is None else max(1, int(worker_count))
    if cache is not None:
        cache.game_key = buildcache.game_fingerprint(game)
    say(f'{worker_count} worker(s)' + (f', cache {cache.folder}' if cache is not None and cache.folder else ''))
    faces = _Faces(game, assets_dir, worker_count, cache, say)
    # the image files of the teams (photos, crests, kits: Pillow, slow with big source images) are made in a thread
    # pool while the loop edits the database (Pillow releases the GIL); the real faces in worker processes (_Faces);
    # jobs keeps their order for result.loose
    pool = ThreadPoolExecutor(max_workers=worker_count)
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
            db.put(players, row, 'birthdate', _birth_days(pl.birthdate))  # empty = no birth date (day 0)
            if pl.foot:
                db.put(players, row, 'preferredfoot', 2 if pl.foot == 'left' else 1)
            for skill, v in pl.skills.items():
                db.put(players, row, SKILL_FIELDS[skill], v)
            for f, v in {**pl.appearance, **pl.fields}.items():
                db.put(players, row, f, v)
            street = pl.appearance.get(boots.SURFACE_FIELDS['street'])
            for surface in ('turf', 'indoor'):  # projects that only set the street boot: the same one everywhere
                if street is not None and boots.SURFACE_FIELDS[surface] not in pl.appearance:
                    db.put(players, row, boots.SURFACE_FIELDS[surface], street)
            _fit_body_type(db, players, row)
            if not pl.generic and pl.face is not None:
                db.put(players, row, 'headclasscode', 0)
        except (BuildError, ValueError, KeyError) as e:
            raise BuildError(f'{pl.shown_name}: {e}', pl.uid) from e
        if not pl.generic and pl.face is not None:
            jobs.append(faces.submit(pl, pid, db.get(players, row, 'haircolorcode')))
        db.append('players', row, raw)
        say(f'   player {pid} {pl.shown_name}')
        return pid

    step('leagues', len(project.leagues), len(project.leagues))
    for k, tm in enumerate(project.new_teams):
        step('teams', k, len(project.teams))
        lids = _team_league_ids(tm, league_ids, existing)
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
        say(f'team "{tm.name}" -> teamid {tid} (leagues {lids})')
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
        # a role left unset: the captain, or the first outfield player when the captain is the goalkeeper (a
        # goalkeeper takes a set piece only when the project says so)
        positions = {pids[ref]: first_position.get(ref) for ref, _ in members}
        unset = set_piece_fallback(captain, [pids[ref] for ref, _ in members], positions)
        for role, f in TAKER_ROLES.items():
            db.put(teams, row, f, pids.get(tm.takers.get(role), unset))
        for n, rgb in (('1', primary), ('2', secondary), ('3', primary)):
            for ch, v in zip('rgb', rgb):
                db.put(teams, row, f'teamcolor{n}{ch}', v)
        db.insert_sorted('teams', 'teamid', row, raw)
        bank_teams.add(tid)
        _lineup_rows(db, tid, tm.lineups, pids, [ref for ref, _ in members])
        stadiums = db.table('teamstadiumlinks')
        for k in db.rows('teamstadiumlinks', 'teamid', tm.template):
            r = list(stadiums.records[k])
            db.put(stadiums, r, 'teamid', tid)
            db.append('teamstadiumlinks', r, stadiums.raw_records[k])
        league_links = db.table('leagueteamlinks')
        k = db.rows('leagueteamlinks', 'teamid', tm.template)[0]
        _set_team_leagues(db, tid, lids, (league_links.records[k], league_links.raw_records[k]))
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
                _real_kit_fields(db, team_kits, r, real, fonts)
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
            _real_kit_fields(db, team_kits, r, goalkeeper, fonts)
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
                jobs.append(pool.submit(_real_kit_files, game, tid, kind_n, real, assets_dir, crest_img, tm.uid,
                                        cache))
            elif kind != 'goalkeeper':
                jobs.append(pool.submit(_kit_files, game, tid, kind_n, kits[kind], crest_img))

    # ---- players only in the game's teams or in the World Tour: records cloned from the default template team
    default_links = [links.records[k] for k in db.rows('teamplayerlinks', 'teamid', model.DEFAULT_TEMPLATE_TEAM)]
    picked = {s.player for s in project.world_tour.slots}
    for k, pl in enumerate(pl for pl in project.new_players if pl.uid not in player_ids and (pl.teams or pl.uid in picked)):
        build_player(pl, db.get(links, default_links[k % len(default_links)], 'playerid'), pl.shown_name)

    # ---- the game's players edited in place (same playerid): their row, photo and head, only what changed
    original_jobs = set()
    for pl in project.original_players:
        for job in _build_original_player(db, game, pl, assets_dir, nameid, faces, say):
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
        lids = _team_league_ids(tm, league_ids, existing)
        for job in _build_original_team(db, game, tm, assets_dir, lids, texts, say, player_ids, cache, fonts):
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
        faces.close()
    step('images', len(jobs), len(jobs))
    if cache is not None and cache.folder:
        removed = cache.prune()
        say(f'cache: {cache.hits} reused, {cache.misses} made, {removed} old entries removed')

    _build_boots(db, game, project, assets_dir, player_ids, entries, result, say, boot_converter)
    _build_gloves(db, game, project, assets_dir, player_ids, entries, result, say, glove_converter)
    _set_preferred_positions(db, game, project, player_ids, result, say)
    _build_balls(db, game, project, assets_dir, entries, result, say, ball_converter)
    apply_original_changes(db, project.originals)
    try:
        world_tour.apply(db, game, project, player_ids, result.loose, entries, texts, say)
    except world_tour.WorldTourError as e:
        raise BuildError(f'World Tour: {e}') from e
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
        entries.update(gamepatches.entries(game, project.game_patches, project.world_tour))
    except gamepatches.GamePatchError as e:
        raise BuildError(str(e)) from e
    say(f'database {len(out)} bytes; {len(texts)} texts; {len(entries)} replaced entries')
    result.database = out
    result.entries = entries
    return result


BUILD_STATE = '.fsmod_build.json'  # inside the patch folder: what the reused archives contain

# How the patch replaces files that live inside the game's archives (changed 10/11/2026):
#   'loose'    (default after 0.4.0) every replaced entry is a loose file Game/<entry name> and its 20-byte record is
#              zeroed in a copy of the original .bh: the game then misses it in the .big and opens the loose file.
#              The .big files never go in the patch (~50 MB instead of ~2 GB). Validated in game (ReStreet 2.1.4)
#              for data0 (database, Lua script), data1 (menu crest, BIGF screen), data3 (face texture) and
#              2dheads (photo); data7 follows the same .bh lookup but was not seen in game yet.
#   'archives' (up to 0.4.0) the whole .big files go, with the replaced entries written inside them
#              (write_patch_archives). To go back to it, set PATCH_LAYOUT = 'archives': nothing else changes
#              (install/uninstall work from the file list of the patch).
PATCH_LAYOUT = 'loose'
PATCH_LAYOUTS = ('loose', 'archives')


def write_patch(result, game, out_dir, progress=None):
    """Writes the patch into out_dir, mirroring the game root (copy each folder over the game's folder), in the
    layout of PATCH_LAYOUT: write_patch_loose or write_patch_archives."""
    if PATCH_LAYOUT == 'archives':
        return write_patch_archives(result, game, out_dir, progress)
    if PATCH_LAYOUT != 'loose':
        raise BuildError(f'unknown patch layout {PATCH_LAYOUT!r} (bug)')
    return write_patch_loose(result, game, out_dir, progress)


def _entries_by_file(result):
    by_file = {}
    for (short, name), data in result.entries.items():
        if short not in PATCH_TARGETS:
            raise BuildError(f'unknown archive {short} (bug)')
        by_file.setdefault(short, {})[name] = data
    return by_file


def _start_patch_dir(out_dir):
    """Reads and removes the build state (rewritten only when the whole write succeeds), keeps only Game/.
    Returns (previous state {short: ...}, Game folder)."""
    import json
    import shutil
    state_path = os.path.join(out_dir, BUILD_STATE)
    previous = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding='utf-8') as f:
                previous = json.load(f).get('files', {})
        except (OSError, ValueError):
            previous = {}
        os.remove(state_path)
    game_out = os.path.join(out_dir, GAME_DATA)
    os.makedirs(game_out, exist_ok=True)
    for entry in os.listdir(out_dir):  # old layouts (GameData/, Mods/) and stray files
        if entry != GAME_DATA:
            path = os.path.join(out_dir, entry)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    return previous, game_out


def _write_whole_archive(game, short, items, dst, prev):
    """Writes the archive short whole into dst: the original with items {entry name: bytes} inside it, and its .bh
    when it has one. An entry that fits its original space is written in place (zero padded; the index keeps the
    original size); a bigger one is appended at the end (aligned to 0x40) and its offset/size are updated in the
    BIG4 header and in the .bh, like ReStreet's installer does for data1.big (validated in game).
    prev: this archive's state from the last build; when its source is the same and dst is still there, dst is
    reused (the ranges written last time and the header are restored from the original, the appended tail is cut),
    so data3.big (1.1 GB) is not copied on every build. Returns (paths written, state of this archive)."""
    import shutil
    src = game.target_path(short)
    toc, hdr_len = big.read_toc_positions(src)
    st = os.stat(src)
    source = [st.st_size, st.st_mtime_ns]
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
    written = [dst]

    index = game.index_path(short)
    if index:
        with open(index, 'rb') as f:
            bh = bytearray(f.read())
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
        written.append(bh_dst)
    return written, {'source': source, 'ranges': ranges, 'moved': sorted(moved)}


def zeroed_index(game, short, names):
    """Bytes of the original .bh of archive short with the 20-byte records of names zeroed (offset, size, 0,
    unknown, hash): the game no longer finds them in the .big and opens Game/<name> from disk. The .bh lists the
    entries in the order of the .big's header; each record's hash is checked before it is zeroed."""
    with open(game.index_path(short), 'rb') as f:
        bh = bytearray(f.read())
    order = {n: i for i, (n, _, _) in enumerate(big.read_toc_file(game.target_path(short)))}
    for name in names:
        if name not in order:
            raise BuildError(f'{name} is not in {short} (bug)')
        pos = 16 + 20 * order[name]
        if struct.unpack('>I', bh[pos + 16:pos + 20])[0] != big.djb2(name.encode()):
            raise BuildError(f'{name}: its record in {os.path.basename(game.index_path(short))} does not match (bug)')
        bh[pos:pos + 20] = bytes(20)
    return bytes(bh)


def _write_file(path, data, written):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    written.add(os.path.normcase(path))


def _finish_patch_dir(out_dir, game_out, written, state, progress_total, step):
    """Removes files of earlier builds and empty folders, then writes the build state."""
    import json
    for root, dirs, files in os.walk(game_out, topdown=False):
        for n in files:
            if os.path.normcase(os.path.join(root, n)) not in written:
                os.remove(os.path.join(root, n))
        for d in dirs:
            path = os.path.join(root, d)
            if not os.listdir(path):
                os.rmdir(path)
    with open(os.path.join(out_dir, BUILD_STATE), 'w', encoding='utf-8') as f:
        json.dump({'layout': PATCH_LAYOUT, 'files': state}, f, indent=2)
    step('files', progress_total, progress_total)


def write_patch_loose(result, game, out_dir, progress=None):
    """Writes the patch into out_dir (PATCH_LAYOUT 'loose', since 10/11/2026), mirroring the game root:

      Game/data8.big, Game/data8.bh            database (the game reads d:\\data8.big over data0; unchanged)
      Game/<.bh of every archive that has one> always: the original .bh with the records of the replaced entries
                                                zeroed, or the plain original when nothing of it is replaced
                                                (data0.bh, data1.bh, data3.bh, data7.bh, .../2dheads.bh)
      Game/<entry name>                         every replaced entry (result.entries of an archive with a .bh) as a
                                                loose file with the same bytes it would have inside the .big
      Game/data/loc/locale*.big                 whole (no .bh, so no zeroing): the original with the new texts
      Game/<internal name>                      loose files (result.loose), as before

    The .big files of data0/1/3/7 and 2dheads never go: the game keeps its own (they must be the originals; the
    install of the app puts them back when an earlier patch had replaced them). Every .bh goes even when it is the
    original, so copying Game/ over any earlier install of this layout still leaves the game as this project says
    (decision of the user, 21/10/2026). To write the old layout instead: PATCH_LAYOUT = 'archives'.
    progress(step, done, total): step 'files' (the archives one by one, then the database and the loose files).
    """
    by_file = _entries_by_file(result)
    previous, game_out = _start_patch_dir(out_dir)
    step = progress or (lambda *_: None)
    files_total = len(PATCH_TARGETS) + 1
    written, state, entry_files = set(), {}, {}
    loose_names = {n.lower() for n in result.loose}
    for k, short in enumerate(sorted(PATCH_TARGETS)):
        step('files', k, files_total)
        items = by_file.get(short, {})
        dst = os.path.join(game_out, PATCH_TARGETS[short])
        if game.index_path(short) is None:  # locale: no index to zero, the archive goes whole
            paths, state[short] = _write_whole_archive(game, short, items, dst, previous.get(short))
            written.update(os.path.normcase(p) for p in paths)
            continue
        _write_file(dst[:-4] + '.bh', zeroed_index(game, short, sorted(items)), written)
        for name, data in items.items():
            key = name.lower()
            if key in entry_files or key in loose_names:
                raise BuildError(f'{name} would be written twice (bug)')
            entry_files[key] = short
            _write_file(os.path.join(game_out, *name.split('/')), data, written)

    step('files', len(PATCH_TARGETS), files_total)
    big_data, bh_data = big.build_patch([(DB_ENTRY, result.database)], game.db_bh_unknown)
    _write_file(os.path.join(game_out, 'data8.big'), big_data, written)
    _write_file(os.path.join(game_out, 'data8.bh'), bh_data, written)
    for name, data in result.loose.items():
        _write_file(os.path.join(game_out, *name.split('/')), data, written)
    _finish_patch_dir(out_dir, game_out, written, state, files_total, step)
    return out_dir


def write_patch_archives(result, game, out_dir, progress=None):
    """Writes the patch into out_dir (PATCH_LAYOUT 'archives': the layout up to 0.4.0), mirroring the game root:

      Game/data8.big, Game/data8.bh            database (the game reads d:\\data8.big over data0)
      Game/<path of every PATCH_TARGETS file>   whole archive: the original with the new entries, or the plain
                                                original when the project changes nothing in it
                                                (data0.big, data1.big, data3.big, data7.big, data/loc/locale*.big,
                                                .../2dheads.big; data0 only changes with fsmod.gamepatches)
      Game/<its .bh>                            always, for the archives that have one (dataN.bh, 2dheads.bh)
      Game/<internal name>                      loose files (result.loose): the game opens d:/<name> from disk
                                                when no archive has it (validated with a country flag, 20/10)

    How each entry goes into its archive: _write_whole_archive (archives are reused between builds through
    BUILD_STATE, so data3.big (1.1 GB) and data7.big are not copied on every build).
    Anything else in out_dir is removed.
    Every target always goes, changed or not: copying Game/ over any earlier install (or over a mod built before)
    then always leaves the game exactly as this project says (decision of the user, 21/10/2026).
    progress(step, done, total): step 'files' (the archives one by one, then the database and the loose files).
    """
    by_file = _entries_by_file(result)
    previous, game_out = _start_patch_dir(out_dir)
    step = progress or (lambda *_: None)
    files_total = len(PATCH_TARGETS) + 1
    written, state = set(), {}
    for k, short in enumerate(sorted(PATCH_TARGETS)):
        step('files', k, files_total)
        dst = os.path.join(game_out, PATCH_TARGETS[short])
        paths, state[short] = _write_whole_archive(game, short, by_file.get(short, {}), dst, previous.get(short))
        written.update(os.path.normcase(p) for p in paths)

    step('files', len(PATCH_TARGETS), files_total)
    big_data, bh_data = big.build_patch([(DB_ENTRY, result.database)], game.db_bh_unknown)
    _write_file(os.path.join(game_out, 'data8.big'), big_data, written)
    _write_file(os.path.join(game_out, 'data8.bh'), bh_data, written)
    for name, data in result.loose.items():
        _write_file(os.path.join(game_out, *name.split('/')), data, written)
    _finish_patch_dir(out_dir, game_out, written, state, files_total, step)
    return out_dir
