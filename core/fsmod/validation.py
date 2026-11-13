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

from . import balls, boots, builder, gloves, kit, kitfonts, model, original_league, original_team, scanface
from .catalog import POSITIONS, SKILLS
from .model import FRIENDLY_TEAM_SIZES, REAL_KIT_FILES

# lengths the game's text slots are meant for (longer texts overflow in some screens)
GOALKEEPER_POSITION = 0  # teamplayerlinks.position GK (catalog.POSITIONS)
REAL_KIT_KINDS = {'home': 0, 'away': 1, 'goalkeeper': 2}  # teamkits.teamkittypetechid of each real kit slot
KIT_FONT_FIELDS = {'number_font': 'numberfonttype', 'shorts_number_font': 'shortsnumberfonttype'}
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


# the game's selector hides them and the World Tour tables do not use their teams (Rest of World, Street Video-Temp)
INTERNAL_LEAGUES = {76, 2095}


def validate(project, catalog, assets_dir):
    # teams taken out of their league (no league) are left out of the patch: said once, not validated
    without_league = [tm.uid for tm in project.teams if not tm.leagues and not tm.hidden]
    every_boot = {b.uid: b for b in project.boots}
    every_glove = {g.uid: g for g in project.gloves}
    every_ball = {b.uid: b for b in project.balls}
    every_team = {lk.team for p in project.players for lk in p.teams}
    hidden_in = {team: project.hidden_in(team) for team in every_team}  # left out in a team: a role falls back
    project = project.visible()  # hidden leagues/teams are left out of the patch: not validated
    issues = [Issue('team_without_league', 'warning', uid, 'leagues', {}) for uid in without_league]
    # a player whose boot is out of the patch keeps the game boot of his code on that surface
    issues += [Issue('boot_hidden', 'warning', p.uid, f'boots.{surface}', {'boot': every_boot[uid].name})
               for p in project.players for surface, uid in p.boots.items()
               if uid in every_boot and every_boot[uid].hidden]
    # a player whose glove is out of the patch keeps his glove code (he stays a goalkeeper)
    issues += [Issue('glove_hidden', 'warning', p.uid, 'glove', {'glove': every_glove[p.glove].name})
               for p in project.players if isinstance(p.glove, str) and p.glove in every_glove
               and every_glove[p.glove].hidden]
    # a stadium whose ball is out of the patch keeps the game's ball
    issues += [Issue('stadium_ball_hidden', 'warning', every_ball[ref].uid, 'hidden', {'stadium': sid})
               for sid, ref in project.originals.stadium_balls.items()
               if isinstance(ref, str) and ref in every_ball and every_ball[ref].hidden]

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
            if real.name_layout is not None:
                check_range(tm.uid, f'real_kits.{slot}.name_layout', real.name_layout, kit.NAME_LAYOUTS[0],
                            kit.NAME_LAYOUTS[-1])
            fonts = kit.name_fonts(catalog.game)
            if isinstance(real.name_font, int) and real.name_font not in fonts:
                error('real_kit_name_font', tm.uid, f'real_kits.{slot}.name_font', value=real.name_font,
                      min=fonts[0], max=fonts[-1])
            # the kit's own font files (fsmod.kitfonts)
            for font_name, file_field in kitfonts.FONT_PARTS:
                if getattr(real, font_name) != kitfonts.KIT:
                    continue
                path = getattr(real, file_field)
                try:
                    with open(os.path.join(assets_dir, path or ''), 'rb') as f:
                        data = f.read()
                except OSError:
                    error('real_kit_font_missing', tm.uid, f'real_kits.{slot}.{font_name}')
                    continue
                try:
                    (kitfonts.check_name_font if font_name == 'name_font' else kitfonts.check_number_font)(data)
                except kitfonts.FontError as e:
                    error(f'real_kit_{e.code}', tm.uid, f'real_kits.{slot}.{font_name}')
            # a number font must have the digits in the chosen color (no file = a broken texture in game); unset =
            # the font of the team's own teamkits row (original team) or of its template's
            row = kit_row(tm.original_id if tm.is_original else tm.template, REAL_KIT_KINDS[slot])
            for font_name, color_name in (('number_font', 'number_color'), ('shorts_number_font', 'shorts_number_color')):
                color = getattr(real, color_name)
                font = getattr(real, font_name)
                if font is None and row is not None:
                    font = catalog.db.get(catalog.db.table('teamkits'), row, KIT_FONT_FIELDS[font_name])
                if isinstance(font, int) and color in kit.NUMBER_COLORS and not kit.number_font_ok(catalog.game, font, color):
                    error('real_kit_number_font', tm.uid, f'real_kits.{slot}.{font_name}', font=font, color=color)

    def kit_row(teamid, kind):
        """teamkits row of a team's kit kind (the home one when the team has none of that kind), or None."""
        t = catalog.db.table('teamkits')
        rows = {catalog.db.get(t, r, 'teamkittypetechid'): r for k in catalog.db.rows('teamkits', 'teamtechid', teamid)
                for r in [t.records[k]]}
        return rows.get(kind, rows.get(0))

    # a kit's own fonts beyond the free font numbers: the kit keeps a game font (kitfonts.assign_font_ids)
    owners = {}
    for tm in project.teams:
        for slot in ('home', 'away', 'goalkeeper'):
            real = tm.real_kit(slot) if tm.use_real_kits else None
            if real is not None:
                owners[id(real)] = (tm.uid, slot)
    font_bytes = {}

    def read_font(path):
        if path not in font_bytes:
            try:
                with open(os.path.join(assets_dir, path), 'rb') as f:
                    font_bytes[path] = f.read()
            except OSError:
                font_bytes[path] = b''
        return font_bytes[path]

    kits = [tm.real_kit(slot) for tm in project.teams if tm.use_real_kits for slot in ('home', 'away', 'goalkeeper')]
    for real, font_field in kitfonts.without_slot([r for r in kits if r is not None], read_font):
        uid, slot = owners[id(real)]
        warning('real_kit_font_no_slot', uid, f'real_kits.{slot}.{font_field}')

    seen = set()
    for entity in [*project.leagues, *project.teams, *project.players, *project.boots, *project.gloves,
                   *project.balls]:
        if entity.uid in seen:
            error('duplicate_uid', entity.uid, 'uid')
        seen.add(entity.uid)

    # ---- leagues
    new_league_ids = {}
    if len(project.new_leagues) > len(builder.IMAGE_COUNTRIES):
        error('too_many_leagues', None, None, max=len(builder.IMAGE_COUNTRIES))
    edited_leagues = set()
    for lg in project.leagues:
        check_text(lg.uid, 'name', lg.name, catalog.locale_chars, required=True)
        check_text(lg.uid, 'short_name', lg.short_name, catalog.locale_chars, limit=LEAGUE_SHORT_LIMIT)
        if lg.is_original:
            if original_league.editable(catalog, lg.original_id) is None:
                error('original_league_not_found', lg.uid, 'original_id', id=lg.original_id)
            elif lg.original_id in edited_leagues:
                error('original_league_edited_twice', lg.uid, 'original_id', id=lg.original_id)
            edited_leagues.add(lg.original_id)
            continue
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
    left = {}  # teamid -> [uid of the edited game players who left it]
    for p in project.original_players:
        mine = {lk.team for lk in p.teams}
        for link in catalog.player_links(p.original_id):
            if link['team'] not in mine:
                left.setdefault(link['team'], []).append(p.uid)
    # a team nobody plays with can stay small: hidden, or internal (street video, friendly pools) and not moved out
    entries = {tm.original_id: tm for tm in project.original_teams}
    unplayed = {*project.originals.hidden_teams, *(tid for tid, tm in entries.items() if set(tm.leagues) <= INTERNAL_LEAGUES),
                *(t['id'] for t in catalog.teams if t['league'] in INTERNAL_LEAGUES and t['id'] not in entries)}
    game_squads = {}
    for tid in {*joins, *left, *(tm.original_id for tm in project.original_teams)}:
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
        # only when it lost players: some teams of the game have none (Free Agents) and are never played
        if len(squad) < min(builder.MIN_ROSTER, len(catalog.player_ids_in(tid))) and tid not in unplayed:
            entry = entries.get(tid)
            name = entry.name if entry else next(t['name'] for t in catalog.teams if t['id'] == tid)
            if entry:
                error('roster_too_small', entry.uid, 'players', count=len(squad), min=builder.MIN_ROSTER)
            for uid in left.get(tid, []):
                error('team_too_small', uid, 'teams', team=name, count=len(squad), min=builder.MIN_ROSTER)
        game_squads[tid] = squad

    # ---- teams
    league_uids = {lg.uid for lg in project.new_leagues}
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
                street_part = getattr(street, part)
                for piece in street_part.pieces if street_part else []:
                    if part == 'socks' and piece.style == -1:
                        continue  # no socks (the game's own pieces have it, mostly under long trousers)
                    if piece.pattern not in catalog.street_options[part].get(piece.style, []):
                        error('invalid_street_piece', tm.uid, f'street_kits.{kind}.{part}', style=piece.style,
                              pattern=piece.pattern)
        for attr, limit in TEAM_TEXT_LIMITS.items():
            check_text(tm.uid, attr, getattr(tm, attr), catalog.locale_chars, limit=limit)
        if len(set(tm.leagues)) < len(tm.leagues):
            error('league_twice', tm.uid, 'leagues')
        for i, league in enumerate(tm.leagues):  # none: an original team is hidden in the game (team_without_league)
            if isinstance(league, str):
                if league not in league_uids:
                    error('league_not_found', tm.uid, f'leagues.{i}', league=league)
            elif league not in original_leagues:
                error('league_not_found', tm.uid, f'leagues.{i}', league=league)
            elif original_leagues[league]['hidden']:
                warning('league_hidden', tm.uid, f'leagues.{i}', league=league)
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
                    if pid in hidden_in.get(tm.original_id, ()):
                        warning('captain_hidden' if role == 'captain' else 'taker_hidden', tm.uid, role, player=pid)
                    else:
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
        if len(members) < builder.MIN_ROSTER:
            error('roster_too_small', tm.uid, 'players', count=len(members), min=builder.MIN_ROSTER)
        elif len(members) > builder.MAX_ROSTER:
            error('roster_too_large', tm.uid, 'players', max=builder.MAX_ROSTER, count=len(members))
        hidden_here = hidden_in.get(tm.uid, ())  # left out of the patch in this team: the build's fallback takes over
        if tm.captain is not None and tm.captain not in members:
            if tm.captain in hidden_here:
                warning('captain_hidden', tm.uid, 'captain', player=tm.captain)
            else:
                error('captain_not_in_roster', tm.uid, 'captain', player=tm.captain)
        for role, ref in tm.takers.items():
            if ref not in members:
                if ref in hidden_here:
                    warning('taker_hidden', tm.uid, f'takers.{role}', player=ref)
                else:
                    error('taker_not_in_roster', tm.uid, f'takers.{role}', player=ref)
        check_lineups(tm, members, lambda ref: members[ref][0], lambda ref: members[ref][1])

    # ---- teams per league (new + the original ones still in it)
    hidden_teams = set(project.originals.hidden_teams)
    league_teams = Counter(league for tm in project.new_teams for league in set(tm.leagues))
    moved = {tm.original_id: set(tm.leagues) for tm in project.original_teams}
    checked = set(league_teams).union(*moved.values())
    for t in catalog.teams:
        if t['id'] in hidden_teams:
            continue
        for league in moved.get(t['id'], {t['league']}):
            if league in checked:
                league_teams[league] += 1
    for league, count in league_teams.items():
        if count <= builder.MAX_LEAGUE_TEAMS:
            continue
        name = next((lg.name for lg in project.leagues if lg.uid == league), None) if isinstance(league, str)             else original_leagues.get(league, {}).get('name', str(league))
        if isinstance(league, str):
            error('league_too_many_teams', league, None, league=name, count=count, max=builder.MAX_LEAGUE_TEAMS)
        for tm in project.teams:
            if league in tm.leagues:
                error('league_too_many_teams', tm.uid, f'leagues.{tm.leagues.index(league)}', league=name,
                      count=count, max=builder.MAX_LEAGUE_TEAMS)

    # ---- players
    for p in project.players:
        chars = catalog.player_name_chars
        check_text(p.uid, 'first_name', p.first_name, chars, required=True)
        check_text(p.uid, 'last_name', p.last_name, chars, required=True)
        check_text(p.uid, 'display_name', p.display_name, chars)
        check_text(p.uid, 'jersey_name', p.jersey_name, chars)
        if len(p.shown_name) > DISPLAY_NAME_LIMIT:
            warning('text_too_long', p.uid, 'display_name', limit=DISPLAY_NAME_LIMIT, length=len(p.shown_name))
        # a game player without teams stays in the game as a free agent; one picked for the World Tour is exported
        if not p.teams and not p.is_original and not any(s.player == p.uid for s in project.world_tour.slots):
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
        if tm.leagues and all(isinstance(lg, int) and lg in changes.hidden_leagues for lg in tm.leagues):
            warning('team_league_hidden', tm.uid, 'leagues')
    picked = set()
    new_players = {p.uid for p in project.new_players}
    for side, size in FRIENDLY_TEAM_SIZES.items():
        slots = getattr(project.world_tour, side)
        where = f'world_tour.{side}'
        if len(slots) > size:
            error('world_tour_team_too_large', None, where, count=len(slots), max=size)
        for slot in slots:
            if slot.player not in (new_players if isinstance(slot.player, str) else catalog.players_by_id):
                error('world_tour_player_not_found', None, where, id=slot.player)
            if slot.player in picked:
                error('world_tour_player_repeated', None, where, id=slot.player)
            picked.add(slot.player)

    # ---- boots (hidden ones are left out of the patch: not validated)
    game_codes = set(boots.game_codes(catalog.game))
    free_street = len(boots.free_street_codes(catalog.game))
    street_count, edited_boots = 0, {}
    for b in project.boots:
        if not b.name.strip():
            error('required', b.uid, 'name')
        for name in ('mesh', 'texture'):
            path = getattr(b, name)
            if path and not os.path.isfile(os.path.join(assets_dir, path)):
                error('boot_file_not_found', b.uid, name, path=path)
            elif not path and (not b.is_original or b.has_files or b.mesh or b.texture):
                error(f'boot_{name}_missing', b.uid, name)  # an edited game boot may keep the game's files
        if b.is_original:
            if b.original_id not in game_codes:
                error('original_boot_not_found', b.uid, 'original_id', id=b.original_id)
            elif b.original_id in edited_boots:
                error('original_boot_edited_twice', b.uid, 'original_id', id=b.original_id)
            edited_boots[b.original_id] = b
            if b.street:
                error('boot_street_original', b.uid, 'street')
        elif b.street:
            street_count += 1
            if street_count > free_street:
                error('boot_street_full', b.uid, 'street', max=free_street)
    visible_boots = {b.uid: b for b in project.boots}
    for p in project.players:
        for surface, uid in p.boots.items():
            b = visible_boots.get(uid)
            if b is None:
                if uid not in every_boot or every_boot[uid].is_original:
                    error('boot_not_found', p.uid, f'boots.{surface}')
            elif b.is_original:
                error('boot_not_found', p.uid, f'boots.{surface}')
            elif surface == 'street' and not b.street:
                error('boot_not_street', p.uid, f'boots.{surface}', boot=b.name)

    # ---- goalkeeper gloves (hidden ones are left out of the patch: not validated)
    glove_codes = set(gloves.game_codes(catalog.game))
    free_gloves = len(gloves.free_codes(catalog.game))
    new_count, edited_gloves = 0, {}
    for g in project.gloves:
        if not g.name.strip():
            error('required', g.uid, 'name')
        if g.texture and not os.path.isfile(os.path.join(assets_dir, g.texture)):
            error('glove_file_not_found', g.uid, 'texture', path=g.texture)
        elif not g.texture and not g.is_original:
            error('glove_texture_missing', g.uid, 'texture')  # an edited game glove may keep the game's file
        if g.is_original:
            if g.original_id not in glove_codes:
                error('original_glove_not_found', g.uid, 'original_id', id=g.original_id)
            elif g.original_id in edited_gloves:
                error('original_glove_edited_twice', g.uid, 'original_id', id=g.original_id)
            edited_gloves[g.original_id] = g
        else:
            new_count += 1
            if new_count > free_gloves:
                error('glove_slots_full', g.uid, 'hidden', max=free_gloves)
    visible_gloves = {g.uid: g for g in project.gloves}
    for p in project.players:
        if isinstance(p.glove, int):
            if p.glove not in glove_codes:
                error('glove_not_found', p.uid, 'glove')
        elif p.glove is not None:
            g = visible_gloves.get(p.glove)
            if (g is None and (p.glove not in every_glove or every_glove[p.glove].is_original)) or                     (g is not None and g.is_original):
                error('glove_not_found', p.uid, 'glove')

    # ---- balls (hidden ones are left out of the patch: not validated) and the ball of each stadium
    ball_ids = set(balls.game_ids(catalog.game))
    free_balls = len(balls.free_ids(catalog.game))
    new_count, edited_balls = 0, {}
    for b in project.balls:
        if not b.name.strip():
            error('required', b.uid, 'name')
        for f in model.BALL_FILES:
            path = getattr(b, f)
            if path and not os.path.isfile(os.path.join(assets_dir, path)):
                error('ball_file_not_found', b.uid, f, path=path)
        if b.is_original:  # an edited game ball keeps the game's files, or takes both new ones
            if bool(b.mesh) != bool(b.texture):
                error('ball_files_missing', b.uid, 'texture' if b.mesh else 'mesh')
            if b.original_id not in ball_ids:
                error('original_ball_not_found', b.uid, 'original_id', id=b.original_id)
            elif b.original_id in edited_balls:
                error('original_ball_edited_twice', b.uid, 'original_id', id=b.original_id)
            edited_balls[b.original_id] = b
        else:
            for f in model.BALL_FILES:
                if not getattr(b, f):
                    error('ball_files_missing', b.uid, f)
            new_count += 1
            if new_count > free_balls:
                error('ball_slots_full', b.uid, 'hidden', max=free_balls)
    visible_balls = {b.uid: b for b in project.balls}
    stadium_ids = catalog.stadium_ids
    for sid, ref in project.originals.stadium_balls.items():
        field_name = f'originals.stadium_balls.{sid}'
        if sid not in stadium_ids:
            error('stadium_not_found', None, field_name, id=sid)
        elif isinstance(ref, int):
            if ref not in ball_ids:
                error('stadium_ball_not_found', None, field_name, id=sid)
        else:
            b = visible_balls.get(ref)
            if (b is None and (ref not in every_ball or every_ball[ref].is_original)) or (b is not None and b.is_original):
                error('stadium_ball_not_found', None, field_name, id=sid)
    return issues


def has_errors(issues):
    return any(i.severity == 'error' for i in issues)
