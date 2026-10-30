"""Read-only view of the original game data: original leagues/teams/players and the valid values the app
offers (positions, nations, generic appearance codes).

Everything is computed once from the original files and cached (the originals never change while the
app runs).
"""
import datetime
from collections import Counter
from functools import cached_property

from . import builder, locale, preview
from .game import LOCALE_ENTRIES, LOCALE_FILES

# teamplayerlinks.position (FIFA's codes; the game's own players use all of them but 1)
POSITIONS = {0: 'GK', 1: 'SW', 2: 'RWB', 3: 'RB', 4: 'RCB', 5: 'CB', 6: 'LCB', 7: 'LB', 8: 'LWB', 9: 'RDM', 10: 'CDM',
             11: 'LDM', 12: 'RM', 13: 'RCM', 14: 'CM', 15: 'LCM', 16: 'LM', 17: 'RAM', 18: 'CAM', 19: 'LAM', 20: 'RF',
             21: 'CF', 22: 'LF', 23: 'RW', 24: 'RS', 25: 'ST', 26: 'LS', 27: 'LW', 28: 'SUB', 29: 'RES'}
SKILLS = {'ATH': (1, 99), 'DEF': (1, 99), 'DRI': (1, 99), 'GK': (1, 99), 'PAS': (1, 99), 'SHO': (1, 99),
          'SPE': (1, 99), 'TRI': (0, 4), 'overall': (1, 99)}
APPEARANCE_FIELDS = ('headtypecode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'skintypecode',
                     'facialhairtypecode', 'facialhaircolorcode', 'eyecolorcode', 'eyebrowcode', 'sideburnscode',
                     'bodytypecode', 'shoetypecode', 'gkglovetypecode', 'jerseysleevelengthcode', 'socklengthcode')
FREE_AGENTS_TEAM = 111592


def _days_to_iso(days):
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
        """{field: sorted values} used by the game's generic players (values known to render)."""
        t = self.db.table('players')
        generic = [r for r in t.records if self.db.get(t, r, 'headclasscode') == 1]
        return {f: sorted({self.db.get(t, r, f) for r in generic}) for f in APPEARANCE_FIELDS}

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
    def street_options(self):
        """{part: {style: [patterns]}} of the street kit pieces (top/bottom/socks) available in the game."""
        return preview.street_options(self.game)

    def template_street(self, teamid):
        """{'home'|'away': {part: {'style', 'pattern'}}}: the first street piece of each part in a template team's
        teamkits (what the editor starts from when the user customizes a piece)."""
        t = self.db.table('teamkits')
        out = {}
        for k in self.db.rows('teamkits', 'teamtechid', teamid):
            r = t.records[k]
            kind = {0: 'home', 1: 'away'}.get(self.db.get(t, r, 'teamkittypetechid'))
            if kind:
                out[kind] = {part: {'style': self.db.get(t, r, f'{col}_geo_type_1'),
                                    'pattern': self.db.get(t, r, f'{col}_texture_pattern_1')}
                             for part, col in (('top', 'top'), ('bottom', 'bottom'), ('socks', 'sock'))}
        return out

    @cached_property
    def generic_template_players(self):
        """Generic players (headclasscode 1) that can be cloned as new players."""
        return [p['id'] for p in self.players if p['generic_head']]

    @cached_property
    def reserved_player_ids(self):
        """Playerids a new player cannot take (builder.reserved_player_ids)."""
        return builder.reserved_player_ids((p['id'] for p in self.players), self.game)
