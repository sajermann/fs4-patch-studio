"""FIFA patch packages (`*.fifapkg.zip`, format "fifa-patch-package"): leagues, teams and players of a FIFA PC game
exactly as that game has them, made by an external extractor that knows nothing about FIFA Street.

Every conversion to this game happens here: names cleaned to the characters the game can show, appearance codes to the
nearest one this game has, nationality by name to this game's nations, FIFA ratings to the skill bars, kit number
colors to this game's palette, collars this game lacks, substitute positions, a captain among the players that come.

`to_share_zips` turns a package into the three share zips of the app (leagues, teams, players; fsapi.share_service
format), so the import, its review and the files (pictures, kit fonts, real faces) go the same way as any shared zip.
Uids are `<prefix>l<id>`, `<prefix>t<id>` and `<prefix>p<id>` with the source ids: importing the same item again,
from this package or another one of the same game, finds the same entry.
"""
import json
import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field

FORMAT = 'fifa-patch-package'
FORMAT_VERSION = 1
MANIFEST = 'package.json'
DEFAULT_PREFIX = 'fifa14-'
UID_PREFIX = re.compile(r'^[A-Za-z0-9_-]{0,40}$')

# FIFA ratings (neutral names of the package) -> skill bars: weights of each bar
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
KEEPER_MIN_SPE = 45  # a goalkeeper slower than this is too slow to come out of the goal
GOALKEEPER = 0
SUBSTITUTE_POSITIONS = (28, 29)  # FIFA 14 links of substitutes and reserves: the player's own position instead
APPEARANCE_FIELDS = ('headtypecode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'skintypecode',
                     'facialhairtypecode', 'facialhaircolorcode', 'eyecolorcode', 'eyebrowcode', 'sideburnscode',
                     'bodytypecode')
KIT_SLOTS = {'home': 'home', 'away': 'away', 'goalkeeper': 'goalkeeper'}  # package kit role -> real kit slot
VALID_COLLARS = range(0, 15)  # this game has body/jersey_<collar>_* meshes 0-14
DEFAULT_COLLAR = 0
# kit number palette (the same in FIFA 14 and in this game: average ink of kitnumbers_1_<color>)
PALETTE = {
    1: (219, 220, 219), 2: (13, 12, 13), 3: (0, 71, 181), 4: (165, 0, 5), 5: (239, 217, 41), 6: (0, 123, 0),
    7: (255, 134, 0), 8: (126, 24, 189), 9: (87, 50, 16), 10: (244, 129, 181), 11: (119, 14, 5),
    12: (128, 196, 246), 13: (0, 20, 82), 14: (165, 164, 165), 15: (203, 204, 103), 16: (156, 136, 79),
    17: (255, 203, 50), 18: (203, 50, 51), 19: (0, 60, 0),
}
SAME_COLOR = 60  # RGB distance under which a font's ink is taken as its palette color
HEIGHT_RANGE, WEIGHT_RANGE = (150, 277), (50, 177)
# FIFA 14 nation names this game spells another way
NATION_ALIASES = {
    "cote d'ivoire": 'Ivory Coast', 'congo dr': 'DR Congo', 'republic of ireland': 'Ireland Republic',
    'netherlands': 'Holland', 'usa': 'United States', 'korea, republic of': 'Korea Republic',
    'south korea': 'Korea Republic', 'north korea': 'Korea DPR', 'bosnia and herzegovina': 'Bosnia Herzegovina',
    'north macedonia': 'FYR Macedonia', 'cape verde': 'Cape Verde Islands', 'czechia': 'Czech Republic',
    'turkiye': 'Turkey', 'china': 'China PR', 'eswatini': 'Swaziland',
}
CHAR_REPLACEMENTS = {
    '’': "'", '‘': "'", '´': "'", '`': "'", '–': '-', '—': '-', 'ø': 'o', 'Ø': 'O', 'ß': 'ss', 'æ': 'ae',
    'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ł': 'l', 'Ł': 'L', 'đ': 'd', 'Đ': 'D', 'ı': 'i',
}
FONT_STEMS = {'name_font_file': 'name-font', 'number_font_file': 'number-font',
              'shorts_number_font_file': 'shorts-number-font'}  # share_service.font_slots
FACE_PREFIX = 'data/sceneassets/'  # package game paths of face files -> paths inside a face folder


class PackageError(ValueError):
    """A file that is not a package this version can read; `code` names the reason."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


@dataclass
class Rules:
    """What this game accepts (from the app's catalog of the original files)."""
    player_name_bytes: set  # bytes the player name table can encode
    text_bytes: set  # bytes every locale file can encode (team and league texts)
    appearance: dict  # {field: allowed codes}
    nations: dict  # {nation id: [shown name, database name]}
    _nation_by_name: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        for nid, names in self.nations.items():
            for n in names:
                if n:
                    self._nation_by_name.setdefault(fold(n), nid)
        for alias, real in NATION_ALIASES.items():
            if fold(real) in self._nation_by_name:
                self._nation_by_name.setdefault(fold(alias), self._nation_by_name[fold(real)])

    @classmethod
    def from_catalog(cls, catalog):
        return cls(set(catalog.player_name_chars), set(catalog.locale_chars), dict(catalog.appearance_options),
                   dict(catalog.nation_names))

    def nation(self, name) -> int | None:
        return self._nation_by_name.get(fold(name)) if name else None


# ---- texts ------------------------------------------------------------------------------------------------------

def fold(s) -> str:
    nfd = unicodedata.normalize('NFD', str(s or '').lower())
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn' and c.isalnum())


def _fits(c: str, allowed: set) -> bool:
    return all(b in allowed for b in c.encode('utf-8'))


def clean_text(text, allowed: set, limit: int | None = None, quotes: bool = True) -> str:
    """The text with only characters the game can encode: accents dropped when needed, a few look-alikes replaced,
    the rest left out; spaces collapsed, cut to `limit`."""
    out = []
    for c in str(text or ''):
        if _fits(c, allowed):
            out.append(c)
            continue
        stripped = ''.join(ch for ch in unicodedata.normalize('NFD', c) if unicodedata.category(ch) != 'Mn')
        if stripped and all(_fits(ch, allowed) for ch in stripped):
            out.append(stripped)
            continue
        rep = CHAR_REPLACEMENTS.get(c)
        if rep and all(_fits(ch, allowed) for ch in rep):
            out.append(rep)
            continue
        if quotes and c in '“”„' and _fits('"', allowed):
            out.append('"')
    cleaned = re.sub(r'\s+', ' ', ''.join(out)).strip()
    if limit and len(cleaned) > limit:
        cleaned = cleaned[:limit].strip()
    return cleaned


def nearest(value, allowed):
    """The allowed code closest to `value` (the smaller one on a tie)."""
    if not allowed or not isinstance(value, int):
        return value
    return min(allowed, key=lambda a: (abs(a - value), a))


def clamp(value, low_high, default):
    if not isinstance(value, int):
        return default
    return min(low_high[1], max(low_high[0], value))


# ---- values -----------------------------------------------------------------------------------------------------

def skills(attributes: dict, keeper: bool) -> dict:
    a = {k: v for k, v in attributes.items() if isinstance(v, (int, float))}
    get = a.get
    a['defensive_awareness'] = (get('standing_tackle', 50) + get('interceptions', 50)) / 2.0
    out = {}
    for bar, weights in SKILL_WEIGHTS.items():
        out[bar] = min(99, max(1, round(sum(a.get(k, 50) * w for k, w in weights.items()))))
    if keeper:
        out['SPE'] = max(out['SPE'], KEEPER_MIN_SPE)
    out['TRI'] = min(4, int(get('skill_moves', 0)) + 2)
    out['overall'] = min(99, max(1, int(get('overall', 50))))
    return out


def number_color(index, ink) -> int:
    """Palette index for this game: `index` when the font's own ink is that palette color (or unknown), else the
    palette color closest to the ink the file really shows."""
    def distance(x, y):
        return sum((p - q) ** 2 for p, q in zip(x, y)) ** 0.5
    if not isinstance(index, int):
        index = 1
    if not ink or (index in PALETTE and distance(ink, PALETTE[index]) <= SAME_COLOR):
        return index if index in PALETTE else min(PALETTE, key=lambda c: abs(c - index))
    return min(PALETTE, key=lambda c: distance(ink, PALETTE[c]))


def league_short_name(names: dict, rules: Rules) -> str:
    order = [names.get(k) for k in ('abbr15', 'trophy_abbr15', 'full', 'database') if names.get(k)]
    for text in order:
        clean = clean_text(text, rules.text_bytes)
        if len(clean) <= 15:
            return clean
    return clean_text(order[0] if order else '', rules.text_bytes, 15)


def normalize_link(url) -> str | None:
    if not isinstance(url, str) or not url.strip() or any(c.isspace() for c in url.strip()):
        return None
    url = url.strip()
    if '://' not in url:
        url = 'https://' + url
    m = re.match(r'^(https?)://([^/:]+)', url, re.I)
    return url if m and '.' in m.group(2) else None


# ---- reading ------------------------------------------------------------------------------------------------------

def is_package(z: zipfile.ZipFile) -> bool:
    return MANIFEST in z.namelist()


def read_manifest(z: zipfile.ZipFile) -> dict:
    try:
        m = json.loads(z.read(MANIFEST).decode('utf-8'))
    except (KeyError, ValueError, UnicodeDecodeError) as e:
        raise PackageError('invalid_package', str(e))
    if not isinstance(m, dict) or m.get('format') != FORMAT:
        raise PackageError('invalid_package', 'format')
    version = m.get('format_version')
    if not isinstance(version, int) or version < 1:
        raise PackageError('invalid_package', 'format_version')
    if version > FORMAT_VERSION:
        raise PackageError('package_too_new', str(version))
    for key in ('leagues', 'teams', 'players', 'nations'):
        if not isinstance(m.get(key, []), list):
            raise PackageError('invalid_package', key)
    return m


# ---- conversion ---------------------------------------------------------------------------------------------------

class _Converter:
    def __init__(self, z: zipfile.ZipFile, manifest: dict, rules: Rules, prefix: str):
        self.z = z
        self.names = set(z.namelist())
        self.m = manifest
        self.rules = rules
        self.prefix = prefix
        self.files = {'leagues': {}, 'teams': {}, 'players': {}}  # kind -> {share zip name: bytes}
        credits = manifest.get('credits') or {}
        self.credits = (credits.get('text') or '').strip() or None
        self.credits_url = normalize_link(credits.get('url'))
        self.nations = {n.get('source_id'): n for n in manifest.get('nations', []) if isinstance(n, dict)}
        self.league_ids = {lg.get('source_id') for lg in manifest.get('leagues', []) if isinstance(lg, dict)}
        self.teams = {t.get('source_id'): t for t in manifest.get('teams', []) if isinstance(t, dict)}
        self.players = {p.get('source_id'): p for p in manifest.get('players', []) if isinstance(p, dict)}

    def uid(self, kind: str, source_id) -> str:
        return f'{self.prefix}{kind}{source_id}'

    def _copy(self, kind: str, name: str, source) -> str | None:
        """Puts the package file `source` into the share zip of `kind` as `name`; None when the package lacks it."""
        if not isinstance(source, str) or source not in self.names:
            return None
        self.files[kind][name] = self.z.read(source)
        return name

    # ---- leagues
    def league(self, lg: dict) -> dict:
        uid = self.uid('l', lg['source_id'])
        names = {k: v for k, v in (lg.get('names') or {}).items() if isinstance(v, str)}
        images = lg.get('images') or {}
        return {
            'uid': uid,
            'name': clean_text(names.get('full') or names.get('database'), self.rules.text_bytes),
            'short_name': league_short_name(names, self.rules),
            'internal_name': clean_text(names.get('database'), self.rules.text_bytes) or None,
            'league_id': None,
            'image': self._copy('leagues', f'league-{uid}.png', (images.get('logo') or {}).get('image')),
            'wide_image': self._copy('leagues', f'league-{uid}-wide.png', (images.get('banner') or {}).get('image')),
            'wide_image_fit': 'contain',
            'hidden': False,
            'source_names': names,
        }

    # ---- teams
    def kit(self, uid: str, slot: str, k: dict) -> dict | None:
        jersey = self._copy('teams', f'team-{uid}-{slot}-jersey.png', k.get('jersey'))
        shorts = self._copy('teams', f'team-{uid}-{slot}-shorts.png', k.get('shorts'))
        if not jersey or not shorts:
            return None
        name_font = k.get('name_font') or {}
        number_font = k.get('number_font') or {}
        shorts_font = k.get('shorts_number_font') or {}
        collar = k.get('collar')
        real = {
            'jersey': jersey,
            'shorts': shorts,
            'thumbnail': None,
            'name_color': k.get('name_color') or [255, 255, 255],
            'number_color': number_color(number_font.get('color'), number_font.get('ink_color')),
            'shorts_number_color': number_color(shorts_font.get('color'), shorts_font.get('ink_color')),
            'collar': collar if collar in VALID_COLLARS else DEFAULT_COLLAR,
            'front_number': bool(k.get('front_number_placement')),
            'shorts_number': bool(k.get('shorts_number_placement')),
            'name_layout': k.get('name_layout'),
            'name_font': name_font.get('id'),
            'number_font': number_font.get('id'),
            'shorts_number_font': shorts_font.get('id'),
            # FIFA 14 placement 0 = no name on the back
            'show_name': bool(k.get('back_name_placement', 1)),
            'positions': k.get('print_positions'),
        }
        for field_name, font in (('name_font_file', name_font), ('number_font_file', number_font),
                                 ('shorts_number_font_file', shorts_font)):
            source = font.get('file')
            if isinstance(source, str):
                ext = os.path.splitext(source)[1].lower()
                real[field_name] = self._copy('teams', f'team-{uid}-{slot}-{FONT_STEMS[field_name]}{ext}', source)
        if real.get('name_font_file'):
            real['name_font_name'] = name_font.get('family_name')
        return real

    def team(self, t: dict) -> dict:
        uid = self.uid('t', t['source_id'])
        names = {k: v for k, v in (t.get('names') or {}).items() if isinstance(v, str)}
        allowed = self.rules.text_bytes
        name = clean_text(names.get('database') or names.get('full'), allowed)
        base = re.sub(r'\s+[\d\-/]+$', '', name).strip()  # a trailing year range ("1960-65") is not part of a short name
        short = clean_text(names.get('abbr15') or base, allowed, 15)
        roster = [r for r in t.get('roster') or [] if isinstance(r, dict) and r.get('player_id') in self.players]
        roster_uids = [self.uid('p', r['player_id']) for r in roster]
        crest = t.get('crest') or {}
        crest_source = crest.get('image_no_background') if crest.get('preferred') == 'no_background' else None
        real_kits = {}
        for k in t.get('kits') or []:
            slot = KIT_SLOTS.get(k.get('role'))
            if slot and slot not in real_kits:
                kit = self.kit(uid, slot, k)
                if kit:
                    real_kits[slot] = kit
        use_real = 'home' in real_kits or 'away' in real_kits
        overall = {self.uid('p', pid): (p.get('attributes') or {}).get('overall', 0) for pid, p in self.players.items()}
        captain = self.uid('p', t['captain_id']) if t.get('captain_id') else None
        if captain not in roster_uids:
            captain = max(roster_uids, key=lambda u: overall.get(u, 0)) if roster_uids else None
        takers = {}
        for role, pid in (t.get('takers') or {}).items():
            if pid and self.uid('p', pid) in roster_uids:
                takers[role] = self.uid('p', pid)
        colors = t.get('colors') or {}
        out = {
            'uid': uid,
            'name': name,
            'short_name': short,
            'abbreviation': clean_text(names.get('abbr3') or short[:3].upper(), allowed, 3),
            'name_10': clean_text(names.get('abbr10'), allowed, 10) or None,
            'name_7': clean_text(names.get('abbr7'), allowed, 7) or None,
            'leagues': [self.uid('l', lid) for lid in t.get('league_ids') or [] if lid in self.league_ids],
            'primary_color': colors.get('primary') or [0, 0, 0],
            'secondary_color': colors.get('secondary') or [255, 255, 255],
            'crest': self._copy('teams', f'team-{uid}-crest.png', crest_source or crest.get('image')),
            'use_real_kits': use_real,
            'real_kits': real_kits if use_real else {},
            'captain': captain,
            'takers': takers,
            'source_names': names,
            'team_id': None,
            'hidden': False,
        }
        if use_real and self.credits:
            out['kit_credits'] = self.credits
        if use_real and self.credits_url:
            out['kit_credits_url'] = self.credits_url
        return out

    # ---- players
    def nationality(self, p: dict) -> int | None:
        nation = self.nations.get(p.get('nationality_id'))
        found = self.rules.nation(nation.get('name')) if nation else None
        if found is not None:
            return found
        # a player of a national team plays for that nation
        national = {n.get('national_team_id'): n for n in self.nations.values() if n.get('national_team_id')}
        for link in (p.get('raw') or {}).get('teamplayerlinks', []):
            n = national.get(link.get('teamid'))
            if n and (found := self.rules.nation(n.get('name'))) is not None:
                return found
        return None

    def player(self, p: dict) -> dict:
        pid = p['source_id']
        uid = self.uid('p', pid)
        allowed = self.rules.player_name_bytes
        names = p.get('names') or {}
        first, last = clean_text(names.get('first'), allowed, quotes=False), clean_text(names.get('last'), allowed, quotes=False)
        common, jersey = clean_text(names.get('common'), allowed, quotes=False), clean_text(names.get('jersey'), allowed, quotes=False)
        first = first or common or last or 'Unknown'
        last = last or common or first or 'Unknown'
        positions = [x.get('code') for x in p.get('positions') or [] if isinstance(x, dict)]
        main_position = positions[0] if positions else None
        teams = []
        for link in p.get('teams') or []:
            if link.get('team_id') not in self.teams:
                continue
            position = link.get('position')
            if position in SUBSTITUTE_POSITIONS or not isinstance(position, int):
                position = main_position if isinstance(main_position, int) else 28
            teams.append({'team': self.uid('t', link['team_id']), 'number': link.get('jersey_number') or 0,
                          'position': position})
        appearance = {}
        for f in APPEARANCE_FIELDS:
            value = (p.get('appearance') or {}).get(f)
            if isinstance(value, int):
                appearance[f] = nearest(value, self.rules.appearance.get(f) or [])
        face, face_files = None, None
        face_in = p.get('face') or {}
        if face_in.get('files'):
            face_files = {}
            for n, (path, info) in enumerate(sorted(face_in['files'].items())):
                if not path.startswith(FACE_PREFIX) or not isinstance(info, dict):
                    continue
                ext = os.path.splitext(path)[1]
                name = self._copy('players', f'player-{uid}-face-{n}{ext}', info.get('file'))
                if name:
                    face_files[path[len(FACE_PREFIX):]] = name
            if face_files:
                face = {'source_id': pid, 'pack': self.m.get('source', {}).get('patch_name') or 'package'}
                if self.credits:
                    face['credits'] = self.credits
                if self.credits_url:
                    face['credits_url'] = self.credits_url
            else:
                face_files = None
        birthdate = None if p.get('birthdate_suspect') else p.get('birthdate')
        return {
            'uid': uid,
            'first_name': first,
            'last_name': last,
            'display_name': common or None,
            'jersey_name': jersey or None,
            'teams': teams,
            'generic': face is None,
            'height': clamp(p.get('height'), HEIGHT_RANGE, 175),
            'weight': clamp(p.get('weight'), WEIGHT_RANGE, 70),
            'birthdate': birthdate if isinstance(birthdate, str) else None,
            'foot': 'left' if p.get('preferred_foot') == 'left' else 'right',
            'skills': skills(p.get('attributes') or {}, main_position == GOALKEEPER),
            'appearance': appearance,
            'fields': {'nationality': self.nationality(p)},
            'photo': self._copy('players', f'player-{uid}.png', (p.get('photo') or {}).get('image')),
            'face': face,
            'face_files': face_files,
            'player_id': None,
            'hidden': False,
        }

    def convert(self) -> dict:
        def items(key, make):
            out, seen = [], set()
            for item in self.m.get(key, []):
                if isinstance(item, dict) and isinstance(item.get('source_id'), int) and item['source_id'] not in seen:
                    seen.add(item['source_id'])
                    out.append(make(item))
            return out
        return {'leagues': items('leagues', self.league), 'teams': items('teams', self.team),
                'players': items('players', self.player)}


def convert(z: zipfile.ZipFile, rules: Rules, prefix: str = DEFAULT_PREFIX):
    """({kind: [share items]}, {kind: {file name: bytes}}, manifest) of an open package."""
    if not UID_PREFIX.match(prefix or ''):
        raise PackageError('invalid_prefix', prefix)
    manifest = read_manifest(z)
    c = _Converter(z, manifest, rules, prefix)
    return c.convert(), c.files, manifest


def to_share_zips(package, rules: Rules, prefix: str, out_dir: str, name) -> tuple[dict, dict]:
    """Writes one share zip per kind with items (the app's share format) into out_dir as name(kind); returns
    ({kind: path}, summary of the package)."""
    try:
        z = zipfile.ZipFile(package)
    except (zipfile.BadZipFile, OSError) as e:
        raise PackageError('not_a_zip', str(e))
    with z:
        if not is_package(z):
            raise PackageError('not_a_package')
        items, files, manifest = convert(z, rules, prefix)
    paths = {}
    for kind, entries in items.items():
        if not entries:
            continue
        path = os.path.join(out_dir, name(kind))
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as out:
            out.writestr('manifest.json', json.dumps({'type': f'fs4-{kind}', 'version': 1, kind: entries},
                                                      ensure_ascii=False))
            for fname, data in files[kind].items():
                out.writestr(fname, data)
        paths[kind] = path
    source = manifest.get('source') or {}
    summary = {'game': source.get('game'), 'patch_name': source.get('patch_name'),
               'credits': (manifest.get('credits') or {}).get('text'), 'created_at': manifest.get('created_at'),
               'counts': {k: len(v) for k, v in items.items()}}
    return paths, summary

