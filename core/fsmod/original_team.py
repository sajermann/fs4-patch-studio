"""Editing one of the game's own teams in place (Team.original_id: same teamid in the game, nothing new created).

load() fills a Team with what the game has, so the editor opens like the edit of a new team: texts (locale), colors
and league (teams / leagueteamlinks), the menu crest (licensed_large/l<id>.dds), the 3D kits as real kits
(jersey_cm / shorts_cm of kit_<id>_<n>_0.rx3, the same textures the app writes, plus the kit-screen thumbnail and the
teamkits fields) and the street kits (first piece of each part in teamkits). The images are written into the project
and a snapshot (Team.loaded) keeps what was loaded.

changes() says what differs from that snapshot; the build (builder._build_original_team) only rewrites that, so an
untouched kit, crest or street kit stays exactly the game's (no DXT re-compression, the up to 5 street pieces the
game picks from kept). Images are compared by content (SHA-1): saving the project renames them.
"""
import hashlib
import io
import os
from dataclasses import dataclass, field

from PIL import Image

from . import chunk, crest, kit, rx3tex
from .model import REAL_KIT_FILES, OriginalSnapshot, RealKit, StreetKit, StreetPart, Team

KIT_SLOTS = (('home', 0), ('away', 1), ('goalkeeper', 2))  # Team.real_kits slot -> teamkittypetechid / kit file
STREET_KINDS = (('home', 0), ('away', 1))
STREET_PARTS = (('top', 'top'), ('bottom', 'bottom'), ('socks', 'sock'))  # StreetKit part -> teamkits column prefix
TEXT_FIELDS = ('name', 'short_name', 'name_10', 'name_7', 'abbreviation')
EDITABLE_FIELDS = (*TEXT_FIELDS, 'leagues', 'primary_color', 'secondary_color', 'use_real_kits', 'kits',
                   'street_kits', 'real_kits')
REAL_KIT_SETTINGS = ('name_color', 'number_color', 'shorts_number_color', 'collar', 'front_number', 'shorts_number')
TAKER_ROLES = {'penalty': 'penaltytakerid', 'free_kick': 'freekicktakerid', 'long_free_kick': 'longkicktakerid',
               'left_corner': 'leftcornerkicktakerid', 'right_corner': 'rightcornerkicktakerid'}  # model.TakerRole


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def _png(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _dds(raw):
    return Image.open(io.BytesIO(chunk.decode(raw)))


def snapshot_fields(tm):
    """The editable fields of a team as JSON, without image paths (images are compared by content)."""
    data = tm.model_dump(mode='json', include=set(EDITABLE_FIELDS))
    for real in data.get('real_kits', {}).values():
        for part in REAL_KIT_FILES:
            real.pop(part, None)
    return data


def game_leaders(db, teamid):
    """(captain, {TakerRole: playerid}) of one of the game's teams, as the game has them."""
    teams = db.table('teams')
    row = teams.records[db.rows('teams', 'teamid', teamid)[0]]
    return db.get(teams, row, 'captainid'), {role: db.get(teams, row, f) for role, f in TAKER_ROLES.items()}


def load(game, catalog, teamid, uid, save_image):
    """Team that edits original team teamid, filled with what the game has. save_image(file name, bytes) stores an
    image in the project and returns its path (the backend's provisional upload)."""
    db = catalog.db
    info = next(t for t in catalog.teams if t['id'] == teamid)
    images = {}

    def keep(key, img, name):
        data = _png(img)
        images[key] = sha1(data)
        return save_image(f'{name}.png', data)

    crest_img = crest.original_crest(game, teamid, 'large')
    crest_path = keep('crest', crest_img.convert('RGBA'), f'crest-{teamid}') if crest_img else None

    kits_t = db.table('teamkits')
    kit_rows = {db.get(kits_t, r, 'teamkittypetechid'): r for r in kits_t.records
                if db.get(kits_t, r, 'teamtechid') == teamid}
    real_kits = {}
    for slot, n in KIT_SLOTS:
        entry = game.read_entry(kit.kit_name(teamid, n))
        if not entry:
            continue
        d = chunk.decode(entry[2])
        fields = {}
        for part, texture in (('jersey', 'jersey_cm'), ('shorts', 'shorts_cm')):
            img = rx3tex.to_image(d, rx3tex.by_name(d, texture)).convert('RGB')
            fields[part] = keep(f'real_kits.{slot}.{part}', img, f'kit-{teamid}-{slot}-{part}')
        thumb = game.read_entry(kit.thumbnail_name(teamid, n))
        if thumb:
            fields['thumbnail'] = keep(f'real_kits.{slot}.thumbnail', _dds(thumb[2]).convert('RGBA'),
                                       f'kit-{teamid}-{slot}-thumbnail')
        row = kit_rows.get(n)
        if row is not None:
            fields.update(
                name_color=tuple(db.get(kits_t, row, f'jerseynamecolor{ch}') for ch in 'rgb'),
                number_color=db.get(kits_t, row, 'numbercolor'),
                shorts_number_color=db.get(kits_t, row, 'shortsnumbercolor'),
                collar=db.get(kits_t, row, 'jerseycollargeometrytype'),
                front_number=bool(db.get(kits_t, row, 'jerseyfrontnumberplacementcode')),
                shorts_number=bool(db.get(kits_t, row, 'shortsnumberplacementcode')))
        real_kits[slot] = RealKit(**fields)

    street_kits = {}
    for kind, n in STREET_KINDS:
        row = kit_rows.get(n)
        if row is None:
            continue
        street_kits[kind] = StreetKit(**{part: StreetPart(
            style=db.get(kits_t, row, f'{col}_geo_type_1'),
            pattern=db.get(kits_t, row, f'{col}_texture_pattern_1'),
            colors=tuple(tuple(db.get(kits_t, row, f'{col}_color_{which}_{ch}') for ch in 'rgb')
                         for which in ('primary', 'secondary', 'tertiary'))) for part, col in STREET_PARTS})

    captain, takers = game_leaders(db, teamid)

    texts = catalog.texts
    name = info['name']
    tm = Team(
        uid=uid, original_id=teamid, name=name, leagues=[info['league']],
        short_name=texts.get(f'TeamName_Abbr15_{teamid}') or name,
        name_10=texts.get(f'TeamName_Abbr10_{teamid}') or name[:10],
        name_7=texts.get(f'TeamName_Abbr7_{teamid}') or name[:7],
        abbreviation=texts.get(f'TeamName_Abbr3_{teamid}') or name[:3].upper(),
        primary_color=tuple(info['primary_color']), secondary_color=tuple(info['secondary_color']),
        crest=crest_path, use_real_kits=bool(real_kits), real_kits=real_kits, street_kits=street_kits,
        captain=captain, takers=takers)
    tm.loaded = OriginalSnapshot(team=snapshot_fields(tm), images=images)
    return tm


@dataclass
class Changes:
    """What an original team entry changes compared with what was loaded from the game."""
    texts: set = field(default_factory=set)  # TEXT_FIELDS that changed
    colors: bool = False
    league: bool = False  # the set of leagues changed
    crest: bool = False
    kits_mode: bool = False  # use_real_kits switched (off: generic kits from the colors)
    kit_colors: bool = False  # Team.kits overrides (generic kits)
    real_kits: dict = field(default_factory=dict)  # slot -> set of 'jersey' / 'shorts' / 'thumbnail' / 'settings'
    street_kits: set = field(default_factory=set)  # 'home' / 'away'

    @property
    def any(self):
        return bool(self.texts or self.colors or self.league or self.crest or self.kits_mode or self.kit_colors
                    or any(self.real_kits.values()) or self.street_kits)


def image_sha1(assets_dir, path):
    if not path:
        return None
    try:
        with open(os.path.join(assets_dir, path), 'rb') as f:
            return sha1(f.read())
    except OSError:
        return None


def snapshot_leagues(fields):
    """Leagues of a snapshot (one taken before a team could be in several leagues has `league`)."""
    if 'leagues' in fields:
        return fields['leagues']
    return [] if fields.get('league') is None else [fields['league']]


def changes(tm, assets_dir):
    """Changes of an original team entry (everything counts as changed when there is no snapshot)."""
    loaded = tm.loaded or OriginalSnapshot()
    before, now = loaded.team, snapshot_fields(tm)
    out = Changes()
    out.texts = {f for f in TEXT_FIELDS if now.get(f) != before.get(f)}
    out.colors = any(now.get(f) != before.get(f) for f in ('primary_color', 'secondary_color'))
    out.league = set(tm.leagues) != set(snapshot_leagues(before))
    out.crest = image_sha1(assets_dir, tm.crest) != loaded.images.get('crest')
    out.kits_mode = now.get('use_real_kits') != before.get('use_real_kits')
    out.kit_colors = now.get('kits') != before.get('kits')
    for slot, _ in KIT_SLOTS:
        real = tm.real_kits.get(slot)
        if real is None:
            continue
        parts = {part for part in REAL_KIT_FILES
                 if image_sha1(assets_dir, getattr(real, part)) != loaded.images.get(f'real_kits.{slot}.{part}')}
        old = before.get('real_kits', {}).get(slot, {})
        if any(now['real_kits'][slot].get(k) != old.get(k) for k in REAL_KIT_SETTINGS):
            parts.add('settings')
        out.real_kits[slot] = parts
    out.street_kits = {kind for kind, _ in STREET_KINDS
                       if now.get('street_kits', {}).get(kind) != before.get('street_kits', {}).get(kind)}
    return out


def untouched(tm, assets_dir, catalog):
    """The entry still has exactly what was loaded from the game (opened without changing anything): the project
    can drop it (the team stays the game's) and the UI shows it as an original, not as an edited one."""
    if tm.loaded is None or tm.hidden or tm.lineups:
        return False
    captain, takers = game_leaders(catalog.db, tm.original_id)
    return tm.captain == captain and tm.takers == takers and not changes(tm, assets_dir).any
