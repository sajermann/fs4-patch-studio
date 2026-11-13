"""Read-only view of the original game data: original leagues/teams/players and the valid values the app
offers (positions, nations, generic appearance codes).

Everything is computed once from the original files and cached (the originals never change while the
app runs).
"""
import datetime
from collections import Counter
from functools import cached_property

from . import balls, boots, builder, chunk, gloves, kit, locale, preview
from .game import LOCALE_ENTRIES, LOCALE_FILES
from .original_team import STREET_PARTS

# teamplayerlinks.position (FIFA's codes; the game's own players use all of them but 1)
POSITIONS = {0: 'GK', 1: 'SW', 2: 'RWB', 3: 'RB', 4: 'RCB', 5: 'CB', 6: 'LCB', 7: 'LB', 8: 'LWB', 9: 'RDM', 10: 'CDM',
             11: 'LDM', 12: 'RM', 13: 'RCM', 14: 'CM', 15: 'LCM', 16: 'LM', 17: 'RAM', 18: 'CAM', 19: 'LAM', 20: 'RF',
             21: 'CF', 22: 'LF', 23: 'RW', 24: 'RS', 25: 'ST', 26: 'LS', 27: 'LW', 28: 'SUB', 29: 'RES'}
SKILLS = {'ATH': (1, 99), 'DEF': (1, 99), 'DRI': (1, 99), 'GK': (1, 99), 'PAS': (1, 99), 'SHO': (1, 99),
          'SPE': (1, 99), 'TRI': (0, 4), 'overall': (1, 99)}
APPEARANCE_FIELDS = ('headtypecode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'skintypecode',
                     'facialhairtypecode', 'facialhaircolorcode', 'eyecolorcode', 'eyebrowcode', 'sideburnscode',
                     'bodytypecode', 'shoetypecode', 'gkglovetypecode', 'jerseysleevelengthcode', 'socklengthcode',
                     'turf_shoe', 'indoor_shoe')
FREE_AGENTS_TEAM = 111592
STADIUM_NO_TIME = 5  # stadiums.timeofday1-4: an empty slot
MAX_HAIR_CODE = 127  # players.hairtypecode has 7 bits; only createplayer's hair style (9 bits) reaches the hairs above it
# The game's own hair categories (CreatePlayerHairLength_<n>; lists in the code of the player creator, 128 hairs).
# Hair 27 is in none of them: some generic players use it, the creator does not offer it.
HAIR_GROUPS = {
    'afro': (1, 2, 3, 4, 5, 6, 28, 45, 46, 47, 60, 71, 82, 96, 97, 109, 110, 203, 303, 308, 311, 313),
    'very_short': (0, 25, 26, 29, 41, 43, 304),
    'short': (16, 17, 18, 19, 21, 22, 23, 24, 31, 36, 37, 38, 39, 40, 54, 61, 64, 65, 69, 70, 72, 75, 77, 78, 85, 86, 88, 90,
              92, 93, 94, 100, 101, 102, 104, 105, 106, 107, 111, 302, 306, 312),
    'medium': (13, 14, 15, 20, 30, 35, 42, 44, 52, 55, 57, 58, 59, 62, 63, 66, 67, 74, 76, 81, 83, 87, 89, 95, 98, 99, 103,
               108, 112, 307, 315),
    'long': (7, 8, 9, 10, 11, 12, 32, 33, 34, 48, 49, 51, 53, 56, 68, 73, 79, 80, 84, 91, 300, 301, 305, 314),
    'helmets': (50, 213),
}


def _days_to_iso(days):
    if days == builder.NO_BIRTHDATE:
        return None
    try:
        return (builder.EPOCH + datetime.timedelta(days=days)).isoformat()
    except OverflowError:
        return None


class Catalog:
    def __init__(self, game):
        self.game = game

    # ---------------------------------------------------------------- raw data
    @cached_property
    def db(self):
        return builder.Db(self.game.original_db(), self.game.meta)

    @cached_property
    def _locale(self):
        return self.game.locale()[1]

    @cached_property
    def texts(self):
        return locale.texts(self._locale)

    @cached_property
    def locale_chars(self):
        """Characters every locale file and language can encode (the texts go into all of them)."""
        return set.intersection(*(locale.charset(self.game.locale(f, e)[1]) for f in LOCALE_FILES for e in LOCALE_ENTRIES))

    @cached_property
    def player_name_chars(self):
        return set(self.db.table('playernames').huff.codes)

    def field_range(self, table, field_name):
        """(min, max) real values a field can hold."""
        f = self.db.table(table).field(field_name)
        return f.rangelow, f.rangelow + (1 << f.depth) - 1

    def has_field(self, table, field_name):
        try:
            self.db.table(table).field(field_name)
            return True
        except KeyError:
            return False

    # ---------------------------------------------------------------- originals
    @cached_property
    def _team_leagues(self):
        t = self.db.table('leagueteamlinks')
        out = {}
        for r in t.records:
            out.setdefault(self.db.get(t, r, 'teamid'), self.db.get(t, r, 'leagueid'))
        return out

    @cached_property
    def _links_by_player(self):
        t = self.db.table('teamplayerlinks')
        out = {}
        for r in t.records:
            out.setdefault(self.db.get(t, r, 'playerid'), []).append(
                {'team': self.db.get(t, r, 'teamid'), 'number': self.db.get(t, r, 'jerseynumber'),
                 'position': self.db.get(t, r, 'position')})
        return out

    @cached_property
    def _links_by_team(self):
        t = self.db.table('teamplayerlinks')
        out = {}
        for r in t.records:
            out.setdefault(self.db.get(t, r, 'teamid'), []).append(
                (self.db.get(t, r, 'playerid'), self.db.get(t, r, 'jerseynumber'), self.db.get(t, r, 'position')))
        return out

    def player_ids_in(self, teamid):
        """Playerids of one of the game's teams (as the game has it)."""
        return {pid for pid, _, _ in self._links_by_team.get(teamid, [])}

    def squad(self, teamid):
        """[{'player', 'number', 'position'}] of one of the game's teams (as the game has it)."""
        return [{'player': pid, 'number': number, 'position': position}
                for pid, number, position in self._links_by_team.get(teamid, [])]

    def player_links(self, playerid):
        """[{'team', 'number', 'position'}] of one of the game's players, in database order."""
        return [dict(link) for link in self._links_by_player.get(playerid, [])]

    def player_defaults(self, project):
        """{player uid: values a new player inherits where the project leaves a field unset} (template player
        record + its link to the player's first new team, `team`), so the UI can show "77 (molde)" instead of just
        "molde"."""
        out = {}
        sources = builder.template_sources(project, lambda teamid: self._links_by_team.get(teamid, []))
        for uid, (pid, number, position, team) in sources.items():
            tpl = self.players_by_id.get(pid)
            if tpl is None:
                continue
            out[uid] = {'template': pid, 'template_name': tpl['display_name'], 'team': team, 'number': number,
                        'position': position,
                        'height': tpl['height'], 'weight': tpl['weight'], 'birthdate': tpl['birthdate'],
                        'foot': tpl['foot'], 'nationality': tpl['nationality'],
                        'skills': tpl['skills'], 'appearance': tpl['appearance']}
        return out

    def fill_template_birthdates(self, data):
        """Projects saved before contract v10, where a new player's empty birth date meant the template's date: that
        date is written in, so the build keeps giving them the same one (since v10 empty = no birth date). Changes
        the project JSON in place; True when it changed something."""
        version = data.get('version')
        if isinstance(version, int) and version >= 10:
            return False
        empty = [p for p in data.get('players', []) if isinstance(p, dict) and p.get('original_id') is None
                 and not p.get('birthdate')]
        if not empty:
            return False
        from . import model
        defaults = self.player_defaults(model.load(data))
        changed = False
        for p in empty:
            date = defaults.get(p.get('uid'), {}).get('birthdate')
            if date:
                p['birthdate'] = date
                changed = True
        return changed

    @cached_property
    def leagues(self):
        t = self.db.table('leagues')
        counts = Counter(self._team_leagues.values())
        out = []
        for r in t.records:
            lid = self.db.get(t, r, 'leagueid')
            out.append({'id': lid, 'name': self.texts.get(f'LeagueName_{lid}') or self.db.get(t, r, 'leaguename'),
                        'short_name': self.texts.get(f'LeagueName_Abbr15_{lid}'),
                        'sort_order': self.db.get(t, r, 'defaultsortorder'), 'country': self.db.get(t, r, 'countryid'),
                        'hidden': lid in builder.HIDDEN_LEAGUES, 'team_count': counts.get(lid, 0)})
        return out

    @cached_property
    def league_ids(self):
        return {lg['id'] for lg in self.leagues}

    @cached_property
    def teams(self):
        t = self.db.table('teams')
        roster = Counter(link['team'] for links in self._links_by_player.values() for link in links)
        out = []
        for r in t.records:
            tid = self.db.get(t, r, 'teamid')
            out.append({
                'id': tid, 'name': self.texts.get(f'TeamName_{tid}') or self.db.get(t, r, 'teamname'),
                'short_name': self.texts.get(f'TeamName_Abbr15_{tid}'),
                'abbreviation': self.texts.get(f'TeamName_Abbr3_{tid}'),
                'league': self._team_leagues.get(tid), 'player_count': roster.get(tid, 0),
                'primary_color': [self.db.get(t, r, f'teamcolor1{c}') for c in 'rgb'],
                'secondary_color': [self.db.get(t, r, f'teamcolor2{c}') for c in 'rgb'],
                'generic': bool(self.db.get(t, r, 'isgeneric')),
                'captain': self.db.get(t, r, 'captainid'),
                'takers': {role: self.db.get(t, r, f) for role, f in builder.TAKER_ROLES.items()},
                'lockable': tid in self._unlockables[builder.UNLOCKABLE_TEAM],
                'locked': self._unlockables[builder.UNLOCKABLE_TEAM].get(tid, False)})
        return out

    @cached_property
    def _unlockables(self):
        """{type: {item id: locked}} of fs4unlockables_defs (the game only honours these rows)."""
        t = self.db.table('fs4unlockables_defs')
        out = {builder.UNLOCKABLE_TEAM: {}, builder.UNLOCKABLE_STADIUM: {}}
        for r in t.records:
            kind, item = self.db.get(t, r, 'type_id'), self.db.get(t, r, 'item_id')
            if kind in out and item:
                out[kind][item] = bool(self.db.get(t, r, 'is_locked'))
        return out

    @cached_property
    def lockable_team_ids(self):
        return set(self._unlockables[builder.UNLOCKABLE_TEAM])

    @cached_property
    def stadiums(self):
        """Stadiums the game can lock (all of them start locked but one)."""
        t = self.db.table('stadiums')
        names = {self.db.get(t, r, 'stadiumid'): self.db.get(t, r, 'name') for r in t.records}
        return sorted(({'id': sid, 'name': self.texts.get(f'StadiumName_{sid}') or names.get(sid) or str(sid),
                        'locked': locked} for sid, locked in self._unlockables[builder.UNLOCKABLE_STADIUM].items()),
                      key=lambda s: s['name'])

    @cached_property
    def team_ids(self):
        return {t['id'] for t in self.teams}

    @cached_property
    def _names(self):
        t = self.db.table('playernames')
        return {self.db.get(t, r, 'nameid'): (r[1] or b'').decode('utf-8', 'replace') for r in t.records}

    @cached_property
    def players(self):
        t = self.db.table('players')
        get = self.db.get
        out = []
        for r in t.records:
            pid = get(t, r, 'playerid')
            first, last = self._names.get(get(t, r, 'firstnameid'), ''), self._names.get(get(t, r, 'lastnameid'), '')
            links = self._links_by_player.get(pid, [])
            out.append({
                'id': pid, 'first_name': first, 'last_name': last,
                'display_name': self._names.get(get(t, r, 'commonnameid')) or f'{first} {last}'.strip(),
                'jersey_name': self._names.get(get(t, r, 'playerjerseynameid')),
                'teams': [link['team'] for link in links],
                'number': links[0]['number'] if links else None,
                'position': links[0]['position'] if links else None,
                'height': get(t, r, 'height'), 'weight': get(t, r, 'weight'),
                'birthdate': _days_to_iso(get(t, r, 'birthdate')),
                'foot': 'left' if get(t, r, 'preferredfoot') == 2 else 'right',
                'nationality': get(t, r, 'nationality'),
                'preferred_position': get(t, r, 'preferredposition1'),
                'generic_head': get(t, r, 'headclasscode') == 1,
                'skills': {k: get(t, r, f) for k, f in builder.SKILL_FIELDS.items()},
                'appearance': {f: get(t, r, f) for f in APPEARANCE_FIELDS}})
        return out

    @cached_property
    def players_by_id(self):
        return {p['id']: p for p in self.players}

    # ---------------------------------------------------------------- valid values
    @cached_property
    def reserved_league_ids(self):
        """Leagueids a new league cannot take (builder.reserved_league_ids)."""
        return builder.reserved_league_ids(self.league_ids, self.texts.keys())

    @cached_property
    def reserved_team_ids(self):
        """Teamids a new team cannot take (builder.reserved_team_ids)."""
        return builder.reserved_team_ids(self.team_ids, self.texts.keys())

    @cached_property
    def nations(self):
        t = self.db.table('nations')
        out = [{'id': self.db.get(t, r, 'nationid'),
                'name': self.texts.get(f'NationName_{self.db.get(t, r, "nationid")}') or self.db.get(t, r, 'nationname')}
               for r in t.records]
        return sorted(out, key=lambda n: n['name'])

    @cached_property
    def nation_names(self):
        """{nation id: [shown name, database name]}: both spellings, to match nationalities written elsewhere."""
        t = self.db.table('nations')
        shown = {n['id']: n['name'] for n in self.nations}
        return {self.db.get(t, r, 'nationid'): [shown[self.db.get(t, r, 'nationid')], self.db.get(t, r, 'nationname')]
                for r in t.records}

    @cached_property
    def appearance_options(self):
        """{field: sorted values} a generic player may have: what the game's generic players use, plus the hair colors
        (player.lua) and the hairs with files that none of them uses."""
        out = dict(self.generic_appearance_options)
        out['haircolorcode'] = list(range(len(preview.HAIR_COLORS)))
        out['hairtypecode'] = sorted({*out['hairtypecode'], *(
            code for code in range(MAX_HAIR_CODE + 1)
            if self.game.locate(f'data/sceneassets/hair/hair_{code}_1_0.rx3')
            and self.game.locate(f'data/sceneassets/hair/hair_{code}_1_textures.rx3'))})
        return out

    @cached_property
    def hair_groups(self):
        """[{key, codes}]: the hairs on offer by the game's categories, in its order; 'other' = the ones in none."""
        options = self.appearance_options['hairtypecode']
        known = {code for codes in HAIR_GROUPS.values() for code in codes}
        groups = {**{key: [c for c in options if c in codes] for key, codes in HAIR_GROUPS.items()},
                  'other': [c for c in options if c not in known]}
        return [{'key': key, 'codes': codes} for key, codes in groups.items() if codes]

    @cached_property
    def generic_appearance_options(self):
        """{field: sorted values} used by the game's generic players: the natural looks, for random picks and
        suggestions (no green hair)."""
        t = self.db.table('players')
        generic = [r for r in t.records if self.db.get(t, r, 'headclasscode') == 1]
        out = {f: sorted({self.db.get(t, r, f) for r in generic}) for f in APPEARANCE_FIELDS}
        # boots: any game boot works on any surface, but the street only takes boots.STREET_CODES
        codes = boots.game_codes(self.game)
        for surface, f in boots.SURFACE_FIELDS.items():
            out[f] = [c for c in codes if surface != 'street' or boots.street_ok(c)]
        return out

    @cached_property
    def game_boots(self):
        """The game's own boots: [{code, street (may go on the street), players (how many of the game's players
        wear it on any surface)}], by code."""
        t = self.db.table('players')
        wearers = Counter()
        for r in t.records:
            for code in {self.db.get(t, r, f) for f in boots.SURFACE_FIELDS.values()}:
                wearers[code] += 1
        return [{'code': c, 'street': boots.street_ok(c), 'players': wearers[c]} for c in boots.game_codes(self.game)]

    @cached_property
    def game_gloves(self):
        """The game's own gloves: [{code, players (how many of the game's players have its code; only goalkeepers
        wear it in a match)}], by code."""
        t = self.db.table('players')
        wearers = Counter(self.db.get(t, r, gloves.FIELD) for r in t.records)
        return [{'code': c, 'players': wearers[c]} for c in gloves.game_codes(self.game)]

    @cached_property
    def game_balls(self):
        """The game's own balls: [{id, name (the game's text; None for most of the street balls), stadiums (how many rows
        of stadiums use it: stadiums and country versions)}]."""
        t = self.db.table('stadiums')
        used = Counter(self.db.get(t, r, balls.FIELD) for r in t.records)
        return [{'id': i, 'name': (self.texts.get(f'BallName_{i}') or '').strip() or None, 'stadiums': used[i]}
                for i in balls.game_ids(self.game)]

    @cached_property
    def _stadium_rows(self):
        t = self.db.table('stadiums')
        fields = [f.name for f in t.fields]
        return [{f: self.db.get(t, r, f) for f in fields} for r in t.records]

    @cached_property
    def stadium_ids(self):
        return {r['stadiumid'] for r in self._stadium_rows}

    @cached_property
    def stadium_filters(self):
        """fifaStadiumFilter: the match setups and which stadiums each one offers (by goal type, pitch size and
        walls; validated against the game's menus): [{id, players, goalkeeper, futsal, last_man_standing}]."""
        t = self.db.table('fifaStadiumFilter')
        rows = [{f.name: self.db.get(t, r, f.name) for f in t.fields} for r in t.records]
        return sorted(rows, key=lambda f: f['id'])

    def _stadium_name(self, row):
        """Shown name of a stadiums row: its locale text (some only per time of day), else the database name."""
        sid = row['stadiumid']
        keys = [f'StadiumName_{sid}'] + [f'StadiumName_{sid}_{row[f"timeofday{k}"]}' for k in range(1, 5)]
        return (next((self.texts[k] for k in keys if self.texts.get(k)), None) or row['name'] or str(sid)).strip()

    @cached_property
    def all_stadiums(self):
        """Every stadium of the game: the rows of `stadiums` grouped by renderingbaseid (one stadium, with one row per
        country version when it has them, renderingregionid 1-7), in name order:
        [{id (the first row's stadiumid), name, versions: [{id, region, ball, menu}], in_menu, lockable_id, locked, filters,
        surface, pitch_size, goal_type, walls, capacity, times, free_roam}]. menu = stadiums.hitpitchdefault: the one row
        the game's menus list and an ordinary match loads (validated in game); a stadium without it is not in the menus."""
        lockable = self._unlockables[builder.UNLOCKABLE_STADIUM]
        groups = {}
        for r in sorted(self._stadium_rows, key=lambda r: r['stadiumid']):
            groups.setdefault(r['renderingbaseid'], []).append(r)
        out = []
        for rows in groups.values():
            first = rows[0]
            sid = first['stadiumid']
            locks = [r['stadiumid'] for r in rows if r['stadiumid'] in lockable]
            out.append({
                'id': sid,
                'name': self._stadium_name(first),
                'versions': [{'id': r['stadiumid'], 'region': r['renderingregionid'], 'ball': r[balls.FIELD],
                              'menu': bool(r['hitpitchdefault'])} for r in rows],
                'in_menu': any(r['hitpitchdefault'] for r in rows),
                'lockable_id': locks[0] if locks else None,
                'locked': lockable[locks[0]] if locks else False,
                'filters': [f['id'] for f in self.stadium_filters
                            if f['goaltypemin'] <= first['goaltype'] <= f['goaltypemax']
                            and f['pitchsizemin'] <= first['pitchsize'] <= f['pitchsizemax']
                            and first['wallson'] <= f['wallsonmax']],
                'surface': first['surfacetype'], 'pitch_size': first['pitchsize'], 'goal_type': first['goaltype'],
                'walls': bool(first['wallson']), 'capacity': first['capacity'],
                'times': sorted({r[f'timeofday{k}'] for r in rows for k in range(1, 5)} - {STADIUM_NO_TIME}),
                'free_roam': first['stadiumtype'] == 1,
            })
        return sorted(out, key=lambda s: (s['name'].lower(), s['id']))

    @cached_property
    def positions(self):
        return [{'code': c, 'abbr': a} for c, a in POSITIONS.items()]

    @cached_property
    def lineup_modes(self):
        """Game modes a lineup can be set for (fs4playersareas): [{'players', 'goalkeeper',
        'tactics': {tacticsid: [area per starter slot]}}]; areas: 0 GK, 1 DEF, 2 ATT."""
        t = self.db.table('fs4playersareas')
        modes = {}
        for r in t.records:
            n, gk = self.db.get(t, r, 'numberofplayers'), bool(self.db.get(t, r, 'hasgoalie'))
            areas = [self.db.get(t, r, f'positionareaid{k}') for k in range(n)]
            modes.setdefault((n, gk), {})[self.db.get(t, r, 'tacticsid')] = areas
        return [{'players': n, 'goalkeeper': gk, 'tactics': dict(sorted(tactics.items()))}
                for (n, gk), tactics in sorted(modes.items(), key=lambda m: (-m[0][0], not m[0][1]))]

    @cached_property
    def kit_fonts(self):
        """Fonts a real kit can use: {'name': [{'id', 'name'}] (jerseyfonts/font_<id>.ttf, the font's own name),
        'number': {font: [palette colors it has digits in]} (kitnumbers_<font>_<color>.rx3)}."""
        import io
        from PIL import ImageFont
        names = []
        for n in kit.name_fonts(self.game):
            try:
                data = chunk.decode(self.game.read_entry(kit.NAME_FONT_FILE.format(n))[2])
                family, style = ImageFont.truetype(io.BytesIO(data), 12).getname()
                name = ' '.join(p for p in (family.strip(), (style or '').strip()) if p and p != 'Regular')
            except Exception:  # an unreadable font still has its number
                name = None
            names.append({'id': n, 'name': name})
        numbers = {}
        for font in range(64):
            colors = [c for c in kit.NUMBER_COLORS if kit.number_font_ok(self.game, font, c)]
            if colors:
                numbers[font] = colors
        return {'name': names, 'number': numbers}

    @cached_property
    def kit_print(self):
        """{teamid: {kit kind 0/1/2: {name_font, number_font, shorts_number_font, name_layout}}} of every team's
        teamkits rows: what a real kit keeps when it does not set its own (RealKit fields left empty)."""
        t = self.db.table('teamkits')
        fields = {'name_font': 'jerseynamefonttype', 'number_font': 'numberfonttype',
                  'shorts_number_font': 'shortsnumberfonttype', 'name_layout': 'jerseynamelayouttype'}
        out = {}
        for r in t.records:
            kind = self.db.get(t, r, 'teamkittypetechid')
            if kind in (0, 1, 2):
                out.setdefault(self.db.get(t, r, 'teamtechid'), {})[kind] = {
                    k: self.db.get(t, r, f) for k, f in fields.items()}
        return out

    @cached_property
    def street_options(self):
        """{part: {style: [patterns]}} of the street kit pieces (top/bottom/socks) available in the game."""
        return preview.street_options(self.game)

    @cached_property
    def street_pieces_in_use(self):
        """{part: [{'style', 'pattern'}]}: the street pieces some game team wears (home or away) and the game has
        files for, in order: the pool a team without street kits of its own draws from (model.random_street_kits)."""
        t = self.db.table('teamkits')
        options = self.street_options
        out = {}
        for part, col, slots in STREET_PARTS:
            seen = {(self.db.get(t, r, f'{col}_geo_type_{n}'), self.db.get(t, r, f'{col}_texture_pattern_{n}'))
                    for r in t.records if self.db.get(t, r, 'teamkittypetechid') in (0, 1)
                    for n in range(1, slots + 1)}
            out[part] = [{'style': s, 'pattern': p} for s, p in sorted(seen) if p in options[part].get(s, ())]
        return out

    def template_street(self, teamid):
        """{'home'|'away': {part: [{'style', 'pattern'}]}}: the street pieces of each part in a template team's
        teamkits (what the game picks from, and what the editor starts from when the user customizes a part)."""
        t = self.db.table('teamkits')
        out = {}
        for k in self.db.rows('teamkits', 'teamtechid', teamid):
            r = t.records[k]
            kind = {0: 'home', 1: 'away'}.get(self.db.get(t, r, 'teamkittypetechid'))
            if kind:
                out[kind] = {part: [{'style': self.db.get(t, r, f'{col}_geo_type_{n}'),
                                     'pattern': self.db.get(t, r, f'{col}_texture_pattern_{n}')}
                                    for n in range(1, slots + 1)]
                             for part, col, slots in STREET_PARTS}
        return out

    @cached_property
    def generic_template_players(self):
        """Generic players (headclasscode 1) that can be cloned as new players."""
        return [p['id'] for p in self.players if p['generic_head']]

    @cached_property
    def reserved_player_ids(self):
        """Playerids a new player cannot take (builder.reserved_player_ids)."""
        return builder.reserved_player_ids((p['id'] for p in self.players), self.game)
