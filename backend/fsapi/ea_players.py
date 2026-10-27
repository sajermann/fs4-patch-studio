"""Players base the user points to in the settings (players_base_file): who each EA player id is. Scanned-face packs
name their files only by that id (face_<id>_...), so the face gallery shows and searches the players' names with it.

No base ships with the app: each user makes their own and points to it; without one the faces show only their id. The file is read in place, never written.

CONTRACT (what the app reads; any other field is ignored, so a richer base works too):
    {"players": {"<EA player id>": {"name": "Lamine Yamal", "club": "FC Barcelona", "nationality": "Spain",
                                    "first_name": "Lamine", "last_name": "Yamal", "jersey_name": "Lamine Yamal",
                                    "birth_date": "2007-07-13", "height_cm": 181, "weight_kg": 72,
                                    "preferred_foot": "Left"}}}
  * "players": object whose keys are EA player ids (digits) and whose values are objects; an empty object {} is an
    id the base knows nobody has data for yet and is ignored without a warning;
  * "name": required, non-empty text (what the gallery shows and searches); "club", "nationality": optional text;
  * optional, for "Usar dados da base" on a player (each one is offered only when present and valid):
    "first_name", "last_name", "jersey_name" (text), "birth_date" (YYYY-MM-DD), "height_cm", "weight_kg" (whole
    numbers), "preferred_foot" ("Right" / "Left"), "nationality" (English name, matched to the game's nations);
  * optional, for the skill bars: "attributes" (the FIFA attributes: "acceleration", "sprint_speed", "finishing"...,
    "gk_diving"..., whole numbers 1-99), "skill_moves" (1-5) and "positions" (["GK"] marks a keeper); converted by
    skills() into the game's bars (only when every attribute it needs is there).
Records that break the contract are skipped and reported by check(), so a wrong field name ("player_name" instead
of "name") is visible instead of silently showing nothing.
"""
import json
import os
import re
import unicodedata

SUMMARY_FIELDS = ('name', 'club', 'nationality')  # what the gallery shows of each face
TEXT_FIELDS = SUMMARY_FIELDS + ('first_name', 'last_name', 'jersey_name')
NUMBER_FIELDS = ('height_cm', 'weight_kg')
# FIFA attributes -> FIFA Street bars: the weights of EA's card stats (PAC SHO PAS DRI DEF PHY, +GK). Checked
# against the 2,213 original players (26/10/2026): the means land within ~5 points of the game's, so good enough
# as a starting point the user edits. ATH = physical, SPE = pace, GK = mean of the keeper attributes (no kicking).
SKILL_WEIGHTS = {
    'ATH': {'jumping': .05, 'stamina': .25, 'strength': .5, 'aggression': .2},
    'DEF': {'interceptions': .2, 'heading_accuracy': .1, 'defensive_awareness': .3, 'standing_tackle': .3,
            'sliding_tackle': .1},
    'DRI': {'agility': .1, 'balance': .05, 'reactions': .05, 'ball_control': .3, 'dribbling': .5},
    'GK': {'gk_diving': .25, 'gk_handling': .25, 'gk_positioning': .25, 'gk_reflexes': .25},
    'PAS': {'vision': .2, 'crossing': .2, 'freekick_accuracy': .05, 'short_passing': .35, 'long_passing': .15,
            'curve': .05},
    'SHO': {'positioning': .05, 'finishing': .45, 'shot_power': .2, 'long_shots': .2, 'volleys': .05,
            'penalties': .05},
    'SPE': {'acceleration': .45, 'sprint_speed': .55},
}
ATTRIBUTES = {a for w in SKILL_WEIGHTS.values() for a in w}
KEEPER_MIN_SPE = 45  # the formula gives keepers ~34 pace; the game's keepers average 51
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
# FIFA names (EA's newer editions) the game spells another way (keys folded: lower case, no accents)
NATION_ALIASES = {"cote d'ivoire": 'Ivory Coast', 'congo dr': 'DR Congo', 'republic of ireland': 'Ireland Republic',
                  'netherlands': 'Holland', 'usa': 'United States', 'korea, republic of': 'Korea Republic',
                  'south korea': 'Korea Republic', 'north korea': 'Korea DPR', 'bosnia and herzegovina':
                  'Bosnia Herzegovina', 'north macedonia': 'FYR Macedonia', 'cape verde': 'Cape Verde Islands',
                  'czechia': 'Czech Republic', 'turkiye': 'Turkey', 'china': 'China PR', 'eswatini': 'Swaziland'}
MAX_EXAMPLES = 5  # problems listed by check(); the rest are only counted


class PlayersBaseError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


_cache = {}  # path -> ((size, mtime), players, problems)


def _read(path):
    """({player id: record}, [problem texts]) of a base file; PlayersBaseError when it cannot be used at all."""
    if not path or not os.path.isfile(path):
        raise PlayersBaseError('players_base_not_found', 'Arquivo da base de jogadores não encontrado.')
    st = os.stat(path)
    key = (st.st_size, st.st_mtime_ns)
    hit = _cache.get(path)
    if hit and hit[0] == key:
        return hit[1], hit[2]
    try:
        with open(path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except (OSError, UnicodeError, ValueError) as e:
        raise PlayersBaseError('players_base_invalid_json', f'O arquivo não é um JSON válido ({e}).')
    if not isinstance(data, dict) or 'players' not in data:
        raise PlayersBaseError('players_base_no_players', 'Falta a chave "players" no topo do JSON.')
    if not isinstance(data['players'], dict):
        raise PlayersBaseError('players_base_players_not_object',
                               '"players" precisa ser um objeto { "<id>": { "name": … } }, não uma lista.')
    players, problems = {}, []
    for key_id, rec in data['players'].items():
        if not str(key_id).isdigit():
            problems.append(f'Chave "{key_id}": o id precisa ser só números (id do jogador na EA).')
        elif not isinstance(rec, dict):
            problems.append(f'Jogador {key_id}: precisa ser um objeto com "name".')
        elif not rec:
            continue  # {}: no source knew this id yet, not a mistake
        elif not isinstance(rec.get('name'), str) or not rec['name'].strip():
            other = [k for k in rec if 'name' in k.lower() and k != 'name']
            hint = f' (achei {", ".join(map(repr, other))}; o campo esperado é "name")' if other else ''
            problems.append(f'Jogador {key_id}: falta "name" (texto){hint}.')
        else:
            players[int(key_id)] = _usable(rec)
    _cache[path] = (key, players, problems)
    return players, problems


def _usable(rec):
    """The contract fields of a record that have a valid value (anything else is dropped)."""
    out = {k: rec[k].strip() for k in TEXT_FIELDS if isinstance(rec.get(k), str) and rec[k].strip()}
    out.update({k: rec[k] for k in NUMBER_FIELDS if isinstance(rec.get(k), int) and not isinstance(rec[k], bool)
                and rec[k] > 0})
    if isinstance(rec.get('birth_date'), str) and DATE.fullmatch(rec['birth_date']):
        out['birth_date'] = rec['birth_date']
    if rec.get('preferred_foot') in ('Right', 'Left'):
        out['preferred_foot'] = rec['preferred_foot']
    skills = _skills(rec)
    if skills:
        out['skills'] = skills
    return out


def _number(v, low, high):
    return isinstance(v, int) and not isinstance(v, bool) and low <= v <= high


def _skills(rec):
    """{'ATH'..'SPE': 1-99, 'TRI': 0-4} converted from the record's FIFA attributes, or None when any is missing.
    defensive_awareness (absent in older editions) falls back to the mean of standing_tackle and interceptions."""
    attrs = rec.get('attributes')
    if not isinstance(attrs, dict):
        return None
    attrs = {k: v for k, v in attrs.items() if k in ATTRIBUTES and _number(v, 1, 99)}
    if 'defensive_awareness' not in attrs and {'standing_tackle', 'interceptions'} <= attrs.keys():
        attrs['defensive_awareness'] = (attrs['standing_tackle'] + attrs['interceptions']) / 2
    if not ATTRIBUTES <= attrs.keys():
        return None
    out = {bar: min(99, max(1, round(sum(attrs[a] * w for a, w in weights.items()))))
           for bar, weights in SKILL_WEIGHTS.items()}
    positions = rec.get('positions')
    if isinstance(positions, list) and positions[:1] == ['GK']:
        out['SPE'] = max(out['SPE'], KEEPER_MIN_SPE)
    # skill moves 1-5 -> TRI 0-4 one step up: most of the game's players (keepers too) have TRI 4
    if _number(rec.get('skill_moves'), 1, 5):
        out['TRI'] = min(4, rec['skill_moves'] + 1)
    return out


def nation_id(name, nations):
    """Game nation id of a base nationality (English name, accents/case ignored), or None. `nations` maps each
    nation id to the names the game knows it by."""
    if not isinstance(name, str):
        return None
    wanted = _fold(NATION_ALIASES.get(_fold(name), name))
    return next((nid for nid, names in nations.items() if any(_fold(n) == wanted for n in names)), None)


def check(path):
    """{'players': usable records, 'skipped': records that break the contract, 'problems': first examples}."""
    players, problems = _read(path)
    return {'players': len(players), 'skipped': len(problems), 'problems': problems[:MAX_EXAMPLES]}


def summary(path, player_id):
    """{'name', 'club', 'nationality'} (the ones the base has) of an EA player id, or None (no base, unusable base,
    or an id the base does not know)."""
    if not path:
        return None
    try:
        rec = _read(path)[0].get(player_id)
    except PlayersBaseError:
        return None
    return {k: rec[k] for k in SUMMARY_FIELDS if k in rec} if rec else None


def _fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))


def search(path, q='', limit=50):
    """Players of the base whose id, name or club matches q (accents ignored): {'total', 'items': [summary + id]}."""
    players = _read(path)[0]
    needle = _fold(q.strip())
    rows = [{'id': pid, **{k: rec[k] for k in SUMMARY_FIELDS if k in rec}} for pid, rec in players.items()
            if not needle or needle in str(pid) or needle in _fold(rec['name']) or needle in _fold(rec.get('club', ''))]
    rows.sort(key=lambda r: _fold(r['name']))
    return {'total': len(rows), 'items': rows[:limit]}


def record(path, player_id):
    """Every contract field the base has for one player (for "Usar dados da base"), or None."""
    rec = _read(path)[0].get(player_id)
    return {'id': player_id, **rec} if rec else None
