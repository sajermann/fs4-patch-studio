"""Editing one of the game's own leagues in place (League.original_id: same leagueid, nothing new created).

load() fills a League with what the game has: name and short name (locale LeagueName_<id> /
LeagueName_Abbr15_<id>), order in the league selector (leagues.defaultsortorder) and the images, which are the two
flags of the league's country (fsmod.leaguelogo: the selector shows the country's flag, there is no league logo).
The images are written into the project and a snapshot (League.loaded) keeps what was loaded.

changes() says what differs from that snapshot; the build (builder._build_original_league) only rewrites that. A
changed image replaces the country's flag in place (data1; validated in game with countries 216 and 211), so the
league keeps its country and any other use of that flag changes too (none was seen in game).
"""
from dataclasses import dataclass, field

from . import leaguelogo
from .model import League, OriginalSnapshot
from .original_team import _png, image_sha1, sha1

TEXT_FIELDS = ('name', 'short_name')
EDITABLE_FIELDS = (*TEXT_FIELDS, 'sort_order', 'wide_image_fit')
IMAGES = (('image', 'flag_small'), ('wide_image', 'flag_wide'))  # League field -> leaguelogo asset


def snapshot_fields(lg):
    return lg.model_dump(mode='json', include=set(EDITABLE_FIELDS))


def editable(catalog, leagueid):
    """The game's league leagueid, when it can be edited (the selector shows it), else None."""
    return next((lg for lg in catalog.leagues if lg['id'] == leagueid and not lg['hidden']), None)


def load(game, catalog, leagueid, uid, save_image):
    """League that edits original league leagueid, filled with what the game has. save_image(file name, bytes)
    stores an image in the project and returns its path (the backend's provisional upload)."""
    info = editable(catalog, leagueid)
    if info is None:
        raise KeyError(leagueid)
    images, paths = {}, {}
    for attr, asset in IMAGES:
        entry = game.read_entry(leaguelogo.asset_name(asset, info['country']))
        if not entry:
            continue
        data = _png(leaguelogo.read_image(entry[2])[0].convert('RGBA'))
        images[attr] = sha1(data)
        paths[attr] = save_image(f'league-{leagueid}-{attr}.png', data)
    lg = League(uid=uid, original_id=leagueid, name=info['name'], short_name=info['short_name'] or info['name'],
                sort_order=info['sort_order'], **paths)
    lg.loaded = OriginalSnapshot(team=snapshot_fields(lg), images=images)
    return lg


@dataclass
class Changes:
    """What an original league entry changes compared with what was loaded from the game."""
    texts: set = field(default_factory=set)  # TEXT_FIELDS that changed
    sort_order: bool = False
    images: set = field(default_factory=set)  # 'image' / 'wide_image' (a new fit counts as a new wide image)

    @property
    def any(self):
        return bool(self.texts or self.sort_order or self.images)


def changes(lg, assets_dir):
    """Changes of an original league entry (everything counts as changed when there is no snapshot)."""
    loaded = lg.loaded or OriginalSnapshot()
    before, now = loaded.team, snapshot_fields(lg)
    out = Changes()
    out.texts = {f for f in TEXT_FIELDS if now.get(f) != before.get(f)}
    out.sort_order = now.get('sort_order') != before.get('sort_order')
    out.images = {attr for attr, _ in IMAGES if image_sha1(assets_dir, getattr(lg, attr)) != loaded.images.get(attr)}
    if now.get('wide_image_fit') != before.get('wide_image_fit'):
        out.images.add('wide_image')
    return out


def changed_teams(project, catalog):
    """Leagueids of the game's leagues whose teams the project changes (a team joined or left): they count as edited
    too, with or without an entry of their own (a team's leagues live in the team, not in the league)."""
    game_league = {t['id']: t['league'] for t in catalog.teams}
    out = set()
    for tm in project.teams:
        if tm.hidden and not tm.is_original:
            continue
        mine = {lg for lg in tm.leagues if isinstance(lg, int)}
        game = {game_league.get(tm.original_id)} - {None} if tm.is_original else set()
        out |= mine ^ game
    return sorted(out & catalog.league_ids)


def untouched(lg, assets_dir):
    """The entry still has exactly what was loaded from the game: the project can drop it."""
    return lg.loaded is not None and not lg.hidden and not changes(lg, assets_dir).any
