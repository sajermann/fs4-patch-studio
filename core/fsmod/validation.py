"""Game rules for a Project, checked before saving/building.

validate() never raises: it returns Issues with a stable `code` and `params` so the UI can show its own
(Portuguese) text. Severity 'error' blocks the patch build; 'warning' is informational. A project with
errors can still be saved as a draft.
"""
import datetime
import os
from collections import Counter
from dataclasses import asdict, dataclass, field as dataclass_field
from typing import Optional

from PIL import Image

from . import builder, kit, original_player, original_team, scanface
from .catalog import POSITIONS, SKILLS
from .model import REAL_KIT_FILES

# lengths the game's text slots are meant for (longer texts overflow in some screens)
GOALKEEPER_POSITION = 0  # teamplayerlinks.position GK (catalog.POSITIONS)
TEAM_TEXT_LIMITS = {'short_name': 15, 'name_10': 10, 'name_7': 7, 'abbreviation': 3}
LEAGUE_SHORT_LIMIT = 15
DISPLAY_NAME_LIMIT = 24  # longest player name that still looks fine in game (checked with a 24-character name)


@dataclass
class Issue:
    code: str
    severity: str  # 'error' | 'warning'
    entity: Optional[str] = None  # uid of the league/team/player
    field: Optional[str] = None
    params: dict = dataclass_field(default_factory=dict)

    def to_json(self):
        return asdict(self)


def validate(project, catalog, assets_dir):
    project = project.visible()  # hidden leagues/teams are left out of the patch: not validated
    issues = []

    def error(code, entity=None, field_name=None, **params):
        issues.append(Issue(code, 'error', entity, field_name, params))

    def warning(code, entity=None, field_name=None, **params):
        issues.append(Issue(code, 'warning', entity, field_name, params))

    def check_text(entity, field_name, text, chars, required=False, limit=None):
        if not text or not text.strip():
            if required:
                error('required', entity, field_name)
            return
        # strings are Huffman-coded byte by byte (UTF-8), so every byte of a character needs a code
        bad = sorted({c for c in text if not all(b in chars for b in c.encode('utf-8'))})
        if bad:
            error('invalid_chars', entity, field_name, chars=''.join(bad))
        if limit and len(text) > limit:
            warning('text_too_long', entity, field_name, limit=limit, length=len(text))

    def check_range(entity, field_name, value, low, high):
        if value is not None and not low <= value <= high:
            error('out_of_range', entity, field_name, min=low, max=high, value=value)

    modes = {(m['players'], m['goalkeeper']): m['tactics'] for m in catalog.lineup_modes}
    number_range = catalog.field_range('teamplayerlinks', 'jerseynumber')
    defaults = {}

    def check_lineups(tm, in_roster, position_of, name_of):
        """Lineups per game mode. Any player can take any slot (a field player in goal works); a player no longer in
        the team only warns, the build fills the slot. in_roster: the team's player refs."""
        seen_modes = set()
        for i, lu in enumerate(tm.lineups):
            where = f'lineups.{i}'
            mode = (lu.players, lu.goalkeeper)
            if mode not in modes:
                error('lineup_mode_invalid', tm.uid, where, players=lu.players)
                continue
            if mode in seen_modes:
                error('lineup_mode_repeated', tm.uid, where, players=lu.players)
            seen_modes.add(mode)
            if lu.tactic not in modes[mode]:
                error('lineup_tactic_invalid', tm.uid, f'{where}.tactic', players=lu.players)
            if len(lu.starters) > lu.players:
                error('lineup_too_many_starters', tm.uid, f'{where}.starters', count=len(lu.starters),
                      max=lu.players)
            chosen = [u for u in lu.starters if u is not None]
            if len(set(chosen)) < len(chosen):
                error('lineup_player_repeated', tm.uid, f'{where}.starters', players=lu.players)
            if any(u not in in_roster for u in [*chosen, *lu.reserves]):
                warning('lineup_player_not_in_roster', tm.uid, where, players=lu.players)
            keeper = lu.starters[0] if lu.goalkeeper and lu.starters else None
            if keeper in in_roster:
                position = position_of(keeper)
                if position is not None and position != GOALKEEPER_POSITION:
                    warning('lineup_goalkeeper_not_gk', tm.uid, f'{where}.starters', players=lu.players,
                            player=name_of(keeper))

    def link_position(p, team):
        """Position of a project player in one of his teams (the template's when unset, see player_defaults)."""
        lk = p.link(team)
        if lk is not None and lk.position is not None:
            return lk.position
        if p.is_original:  # the game's player: his position in that team (else in his first one)
            own = {link['team']: link['position'] for link in catalog.player_links(p.original_id)}
            first = next(iter(own.values()), None)
            return own.get(team, first)
        if not defaults:
            defaults.update(catalog.player_defaults(project))
        d = defaults.get(p.uid, {})
        return d.get('position') if d.get('team') == team else None

    def check_real_kits(tm, slots=('home', 'away', 'goalkeeper')):
        for slot in slots:
            real = tm.real_kits.get(slot)
            used = real and any(getattr(real, part) for part in REAL_KIT_FILES)
            if not used:
                if slot != 'goalkeeper':  # no goalkeeper kit = the game's default
                    warning('real_kit_missing', tm.uid, f'real_kits.{slot}', slot=slot)
                continue
            for part in ('jersey', 'shorts'):
                if not getattr(real, part):
                    error('real_kit_file_required', tm.uid, f'real_kits.{slot}.{part}', slot=slot, part=part)
            for part in REAL_KIT_FILES:
                path = getattr(real, part)
                if not path:
                    continue
                try:
                    with Image.open(os.path.join(assets_dir, path)) as im:
                        w, h = im.size
                except OSError:
                    error('real_kit_file_missing', tm.uid, f'real_kits.{slot}.{part}', path=path)
                    continue
                ratio = {'jersey': kit.JERSEY_RATIO, 'shorts': kit.SHORTS_RATIO, 'thumbnail': 1}[part]
                if w != h * ratio:
                    error('real_kit_bad_size', tm.uid, f'real_kits.{slot}.{part}', width=w, height=h,
                          expected='2048×2048' if part == 'jersey' else '2048×1024' if part == 'shorts' else '256×256')
                elif part != 'thumbnail' and w < 1024:
                    warning('real_kit_small', tm.uid, f'real_kits.{slot}.{part}', width=w, height=h)
            for name in ('number_color', 'shorts_number_color'):
                if getattr(real, name) not in kit.NUMBER_COLORS:
                    error('out_of_range', tm.uid, f'real_kits.{slot}.{name}', min=kit.NUMBER_COLORS[0],
                          max=kit.NUMBER_COLORS[-1], value=getattr(real, name))
            check_range(tm.uid, f'real_kits.{slot}.collar', real.collar, kit.COLLARS[0], kit.COLLARS[-1])

    seen = set()
    for entity in [*project.leagues, *project.teams, *project.players]:
        if entity.uid in seen:
            error('duplicate_uid', entity.uid, 'uid')
        seen.add(entity.uid)

    # ---- leagues
    new_league_ids = {}
    if len(project.leagues) > len(builder.IMAGE_COUNTRIES):
        error('too_many_leagues', None, None, max=len(builder.IMAGE_COUNTRIES))
    for lg in project.leagues:
        check_text(lg.uid, 'name', lg.name, catalog.locale_chars, required=True)
        check_text(lg.uid, 'short_name', lg.short_name, catalog.locale_chars, limit=LEAGUE_SHORT_LIMIT)
        if lg.league_id is not None:  # given by the build when missing
            if not builder.FIRST_NEW_LEAGUEID <= lg.league_id <= builder.LAST_NEW_LEAGUEID:
                error('league_id_out_of_range', lg.uid, 'league_id', value=lg.league_id,
                      low=builder.FIRST_NEW_LEAGUEID, high=builder.LAST_NEW_LEAGUEID)
            elif lg.league_id in new_league_ids:
                error('league_id_taken', lg.uid, 'league_id', value=lg.league_id)
            new_league_ids.setdefault(lg.league_id, lg.uid)
        if not lg.image and not lg.wide_image:
            warning('league_image_missing', lg.uid, 'image')

    # ---- squads of the game's teams: the game's players (minus the edited ones who left) + project players
    # (new or edited game players) who joined; {player ref: (position, name)}
    edited = {p.original_id: p for p in project.original_players}
    joins = {}  # teamid -> [(entity uid, field, player ref, position, name)]
    for p in project.players:
        for i, lk in enumerate(p.teams):
            if isinstance(lk.team, int) and lk.team in catalog.team_ids:
                joins.setdefault(lk.team, []).append(
                    (p.uid, f'teams.{i}', p.ref, link_position(p, lk.team), p.shown_name))
    game_squads = {}
    for tid in {*joins, *(tm.original_id for tm in project.original_teams)}:
        squad = {p['id']: (p['position'], p['display_name']) for p in catalog.players
                 if tid in p['teams'] and p['id'] not in edited}
        joined = []
        for entity, where, ref, position, name in joins.get(tid, []):
            if ref not in catalog.player_ids_in(tid):
                joined.append((entity, where))
            squad[ref] = (position, name)
        if len(squad) > builder.MAX_ROSTER:
            for entity, where in joined:
                error('team_full', entity, where, count=len(squad), max=builder.MAX_ROSTER)
        game_squads[tid] = squad

    # ---- teams
    league_uids = {lg.uid for lg in project.leagues}
    original_leagues = {lg['id']: lg for lg in catalog.leagues}
    team_uids = {t.uid for t in project.new_teams}
    team_ids = {}
    edited_originals = {}
    for tm in project.teams:
        check_text(tm.uid, 'name', tm.name, catalog.locale_chars, required=True)
        changes = original_team.changes(tm, assets_dir) if tm.is_original else None
        for kind, street in tm.street_kits.items():
            if changes and kind not in changes.street_kits:
                continue  # the game's own pieces, untouched

            for part in ('top', 'bottom', 'socks'):
                piece = getattr(street, part)
                if piece and piece.pattern not in catalog.street_options[part].get(piece.style, []):
                    error('invalid_street_piece', tm.uid, f'street_kits.{kind}.{part}', style=piece.style,
                          pattern=piece.pattern)
        for attr, limit in TEAM_TEXT_LIMITS.items():
            check_text(tm.uid, attr, getattr(tm, attr), catalog.locale_chars, limit=limit)
        if isinstance(tm.league, str):
            if tm.league not in league_uids:
                error('league_not_found', tm.uid, 'league', league=tm.league)
        elif tm.league not in original_leagues:
            error('league_not_found', tm.uid, 'league', league=tm.league)
        elif original_leagues[tm.league]['hidden']:
            warning('league_hidden', tm.uid, 'league', league=tm.league)
        if tm.is_original:
            if tm.original_id not in catalog.team_ids:
                error('original_team_not_found', tm.uid, 'original_id', id=tm.original_id)
            elif tm.original_id in edited_originals:
                error('original_team_edited_twice', tm.uid, 'original_id', id=tm.original_id)
            edited_originals.setdefault(tm.original_id, tm.uid)
            squad = game_squads.get(tm.original_id, {})
            check_lineups(tm, squad, lambda ref: squad[ref][0], lambda ref: squad[ref][1])
            for role, pid in (('captain', tm.captain), *((f'takers.{r}', p) for r, p in tm.takers.items())):
                if pid is not None and pid not in squad:
                    error('captain_not_in_roster' if role == 'captain' else 'taker_not_in_roster', tm.uid, role,
                          player=pid)
            if tm.crest and not os.path.isfile(os.path.join(assets_dir, tm.crest)):
                error('crest_missing', tm.uid, 'crest', path=tm.crest)
            if tm.use_real_kits:
                check_real_kits(tm, [slot for slot, parts in changes.real_kits.items() if parts] +
                                ([] if not changes.kits_mode else ['home', 'away']))
            continue  # roster and ids stay the game's
        if tm.template not in catalog.team_ids:
            error('template_not_found', tm.uid, 'template', id=tm.template)

        crest_bytes = None
        if tm.crest:
            path = os.path.join(assets_dir, tm.crest)
            if os.path.isfile(path):
                with open(path, 'rb') as f:
                    crest_bytes = f.read()
            else:
                error('crest_missing', tm.uid, 'crest', path=tm.crest)
        if not tm.crest:
            error('crest_required', tm.uid, 'crest')
        if tm.use_real_kits:
            check_real_kits(tm)
        if tm.team_id is not None:  # given by the build when missing
            if not builder.FIRST_NEW_TEAMID <= tm.team_id <= builder.LAST_NEW_TEAMID:
                error('team_id_out_of_range', tm.uid, 'team_id', value=tm.team_id,
                      low=builder.FIRST_NEW_TEAMID, high=builder.LAST_NEW_TEAMID)
            elif tm.team_id in catalog.reserved_team_ids:
                error('team_id_in_game', tm.uid, 'team_id', value=tm.team_id)
            elif tm.team_id in team_ids:
                error('team_id_taken', tm.uid, 'team_id', value=tm.team_id)
            team_ids.setdefault(tm.team_id, tm.uid)

        # roster: the project's players of the team, new or the game's own ({Player.ref: (position, name)})
        roster = project.roster(tm.uid)
        members = {p.ref: (link_position(p, tm.uid), p.shown_name) for p in roster}
        numbers = {}
        for p in roster:
            k, lk = next((k, lk) for k, lk in enumerate(p.teams) if lk.team == tm.uid)
            if lk.number is not None:
                if lk.number in numbers:
                    warning('duplicate_number', p.uid, f'teams.{k}.number', number=lk.number,
                            other=numbers[lk.number])
                numbers.setdefault(lk.number, p.uid)
        if not members:
            error('roster_empty', tm.uid, 'players')
        elif len(members) > builder.MAX_ROSTER:
            error('roster_too_large', tm.uid, 'players', max=builder.MAX_ROSTER, count=len(members))
        if tm.captain is not None and tm.captain not in members:
            error('captain_not_in_roster', tm.uid, 'captain', player=tm.captain)
        for role, ref in tm.takers.items():
            if ref not in members:
                error('taker_not_in_roster', tm.uid, f'takers.{role}', player=ref)
        check_lineups(tm, members, lambda ref: members[ref][0], lambda ref: members[ref][1])

    # ---- teams per league (new + the original ones still in it)
    hidden_teams = set(project.originals.hidden_teams)
    league_teams = Counter(tm.league for tm in project.new_teams)
    moved = {tm.original_id: tm.league for tm in project.original_teams}
    checked = set(league_teams) | set(moved.values())
    for t in catalog.teams:
        league = moved.get(t['id'], t['league'])
        if t['id'] not in hidden_teams and league in checked:
            league_teams[league] += 1
    for league, count in league_teams.items():
        if count <= builder.MAX_LEAGUE_TEAMS:
            continue
        name = next((lg.name for lg in project.leagues if lg.uid == league), None) if isinstance(league, str)             else original_leagues.get(league, {}).get('name', str(league))
        if isinstance(league, str):
            error('league_too_many_teams', league, None, league=name, count=count, max=builder.MAX_LEAGUE_TEAMS)
        for tm in project.teams:
            if tm.league == league:
                error('league_too_many_teams', tm.uid, 'league', league=name, count=count,
                      max=builder.MAX_LEAGUE_TEAMS)

    # ---- players
    for p in project.players:
        chars = catalog.player_name_chars
        check_text(p.uid, 'first_name', p.first_name, chars, required=True)
        check_text(p.uid, 'last_name', p.last_name, chars, required=True)
        check_text(p.uid, 'display_name', p.display_name, chars)
        check_text(p.uid, 'jersey_name', p.jersey_name, chars)
        if len(p.shown_name) > DISPLAY_NAME_LIMIT:
            warning('text_too_long', p.uid, 'display_name', limit=DISPLAY_NAME_LIMIT, length=len(p.shown_name))
        if not p.teams and not p.is_original:  # a game player without teams stays in the game as a free agent
            warning('free_agent_not_exported', p.uid, 'teams')
        linked = set()
        for i, lk in enumerate(p.teams):
            where = f'teams.{i}'
            if lk.team in linked:
                error('player_team_repeated', p.uid, where)
            linked.add(lk.team)
            if lk.team not in (team_uids if isinstance(lk.team, str) else catalog.team_ids):
                error('team_not_found', p.uid, where, team=lk.team)
            check_range(p.uid, f'{where}.number', lk.number, *number_range)
            if lk.position is not None and lk.position not in POSITIONS:
                error('invalid_position', p.uid, f'{where}.position', value=lk.position)
        if p.template is not None:
            tpl = catalog.players_by_id.get(p.template)
            if tpl is None:
                error('template_not_found', p.uid, 'template', id=p.template)
            elif not tpl['generic_head']:
                warning('template_not_generic', p.uid, 'template', id=p.template)
        check_range(p.uid, 'height', p.height, *catalog.field_range('players', 'height'))
        check_range(p.uid, 'weight', p.weight, *catalog.field_range('players', 'weight'))
        if p.birthdate:
            try:
                days = (datetime.date.fromisoformat(p.birthdate) - builder.EPOCH).days
                low, high = catalog.field_range('players', 'birthdate')
                if not low <= days <= high:
                    error('out_of_range', p.uid, 'birthdate', value=p.birthdate)
            except ValueError:
                error('invalid_date', p.uid, 'birthdate', value=p.birthdate)
        for skill, value in p.skills.items():
            if skill not in SKILLS:
                error('unknown_skill', p.uid, f'skills.{skill}')
            else:
                check_range(p.uid, f'skills.{skill}', value, *SKILLS[skill])
        loaded_look = p.loaded.player.get('appearance', {}) if p.is_original and p.loaded else {}
        for code, value in p.appearance.items():
            if loaded_look.get(code) == value:
                continue  # the game's own code (scanned heads use codes no generic player has)
            options = catalog.appearance_options.get(code)
            if options is None:
                error('unknown_field', p.uid, f'appearance.{code}')
            elif value not in options:
                error('invalid_appearance', p.uid, f'appearance.{code}', value=value)
        if p.is_original:
            if p.original_id not in catalog.players_by_id:
                error('original_player_not_found', p.uid, 'original_id', id=p.original_id)
            elif p.original_id in edited and edited[p.original_id] is not p:
                error('original_player_edited_twice', p.uid, 'original_id', id=p.original_id)
            if not p.generic and p.face is not None and not original_player.can_take_face(p.original_id):
                error('face_needs_six_digits', p.uid, 'face', id=p.original_id)
        if not p.generic:
            if p.face is None:
                # an original player without a real face keeps the game's scanned head (only if he had one)
                if not (p.is_original and not catalog.players_by_id.get(p.original_id, {}).get('generic_head', True)):
                    error('face_missing', p.uid, 'face')
            else:
                files = scanface.read_files(scanface.project_face_dir(assets_dir, p.uid), p.face.source_id)
                if any(k not in files for k in scanface.REQUIRED):
                    error('face_files_missing', p.uid, 'face', id=p.face.source_id)
        for name, value in p.fields.items():
            if not catalog.has_field('players', name):
                error('unknown_field', p.uid, f'fields.{name}')
            else:
                check_range(p.uid, f'fields.{name}', value, *catalog.field_range('players', name))

    # ---- photos (loose files named by the playerid: any number of them)
    for p in (p for p in project.players if p.teams):
        if p.photo and not os.path.isfile(os.path.join(assets_dir, p.photo)):
            error('photo_missing', p.uid, 'photo', path=p.photo)

    # ---- playerids (given by the build when missing): one per player, in the range of new ids (every id the
    # game uses is below it, see builder.reserved_player_ids)
    seen = {}
    for p in project.new_players:
        if p.player_id is None:
            continue
        if not builder.FIRST_NEW_PLAYERID <= p.player_id <= builder.LAST_NEW_PLAYERID:
            error('player_id_out_of_range', p.uid, 'player_id', value=p.player_id,
                  low=builder.FIRST_NEW_PLAYERID, high=builder.LAST_NEW_PLAYERID)
        elif p.player_id in seen:
            error('player_id_taken', p.uid, 'player_id', value=p.player_id)
        seen.setdefault(p.player_id, p.uid)
    # ---- original leagues, teams and stadiums
    changes = project.originals
    game_hidden = {lg['id'] for lg in catalog.leagues if lg['hidden']}
    for lid in changes.hidden_leagues:
        if lid not in catalog.league_ids or lid in game_hidden:
            error('original_league_not_hideable', None, 'originals.hidden_leagues', id=lid)
    for tid in changes.hidden_teams:
        if tid not in catalog.team_ids:
            error('original_team_not_found', None, 'originals.hidden_teams', id=tid)
    for tid in changes.team_locks:
        if tid not in catalog.lockable_team_ids:
            error('original_team_not_lockable', None, 'originals.team_locks', id=tid)
    lockable_stadiums = {s['id'] for s in catalog.stadiums}
    for sid in changes.stadium_locks:
        if sid not in lockable_stadiums:
            error('stadium_not_lockable', None, 'originals.stadium_locks', id=sid)
    for tm in project.teams:
        if isinstance(tm.league, int) and tm.league in changes.hidden_leagues:
            warning('team_league_hidden', tm.uid, 'league')
    return issues


def has_errors(issues):
    return any(i.severity == 'error' for i in issues)
