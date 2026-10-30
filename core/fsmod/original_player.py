"""Editing the game's own players: load one into a Player entry (Player.original_id) and tell what the user changed.

Same idea as original_team: the entry is filled with what the game has (names, data, skills, appearance codes, teams
with their number and position, menu photo as a PNG) and the build only rewrites what changed, in the player's own
row (same playerid). Head: generic = headclasscode 1 + appearance codes; a scanned head of the game stays as it is
unless the user picks a generic head or a real face of a pack (scanface: only 6-digit playerids).
"""
import hashlib
import io
import os
from dataclasses import dataclass, field

from . import photo
from .model import OriginalPlayerSnapshot, Player, TeamLink

EDITABLE_FIELDS = ('first_name', 'last_name', 'display_name', 'jersey_name', 'height', 'weight', 'birthdate', 'foot',
                   'skills', 'appearance', 'fields', 'generic', 'face')
FIELDS = ('nationality',)  # players columns an original entry carries in Player.fields
FACE_ID_DIGITS = 6  # scanface.convert keeps the template's number of digits (Messi, 158023)


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def snapshot_fields(pl):
    """The editable fields of a player as JSON (the photo is compared by content)."""
    return pl.model_dump(mode='json', include=set(EDITABLE_FIELDS))


def can_take_face(playerid):
    """A real face of a pack can be converted for this playerid (scanface needs FACE_ID_DIGITS digits)."""
    return len(str(playerid)) == FACE_ID_DIGITS


def load(game, catalog, playerid, uid, save_image):
    """Player that edits original player playerid, filled with what the game has. save_image(file name, bytes)
    stores an image in the project and returns its path (the backend's provisional upload)."""
    info = catalog.players_by_id[playerid]
    images = {}
    photo_path = None
    img = photo.original_photo(game, playerid)
    if img is not None:
        buf = io.BytesIO()
        img.convert('RGBA').save(buf, format='PNG')
        images['photo'] = sha1(buf.getvalue())
        photo_path = save_image(f'photo-{playerid}.png', buf.getvalue())
    first, last = info['first_name'], info['last_name']
    shown = info['display_name']
    pl = Player(
        uid=uid, original_id=playerid, first_name=first, last_name=last,
        display_name=shown if shown != f'{first} {last}'.strip() else None,
        jersey_name=info['jersey_name'] if info['jersey_name'] != last else None,
        teams=[TeamLink(**link) for link in catalog.player_links(playerid)],
        generic=info['generic_head'], height=info['height'], weight=info['weight'], birthdate=info['birthdate'],
        foot=info['foot'], skills=dict(info['skills']), appearance=dict(info['appearance']),
        fields={'nationality': info['nationality']}, photo=photo_path)
    pl.loaded = OriginalPlayerSnapshot(player=snapshot_fields(pl), images=images)
    return pl


@dataclass
class Changes:
    """What an original player entry changes compared with what was loaded from the game."""
    fields: set = field(default_factory=set)  # EDITABLE_FIELDS that changed
    photo: bool = False

    @property
    def head(self):
        """The head changed: generic switched or a real face picked/changed (appearance codes count apart)."""
        return bool({'generic', 'face'} & self.fields)

    @property
    def any(self):
        return bool(self.fields or self.photo)


def image_sha1(assets_dir, path):
    if not path:
        return None
    try:
        with open(os.path.join(assets_dir, path), 'rb') as f:
            return sha1(f.read())
    except OSError:
        return None


def changes(pl, assets_dir):
    """Changes of an original player entry (everything counts as changed when there is no snapshot). Teams are not
    compared here: the build compares Player.teams with the game's own links."""
    loaded = pl.loaded or OriginalPlayerSnapshot()
    before, now = loaded.player, snapshot_fields(pl)
    out = Changes()
    out.fields = {f for f in EDITABLE_FIELDS if now.get(f) != before.get(f)}
    out.photo = image_sha1(assets_dir, pl.photo) != loaded.images.get('photo')
    return out


def absorb_game_links(data, load_player):
    """Projects saved while the game's players joined teams through Team.game_players and TeamLink.replaces
    (29/10/2026): both become original player entries, so that a game player's teams live in one place. data: the
    project JSON (changed in place); load_player(playerid) -> Player JSON of a new entry (load()). Returns True when
    something changed."""
    teams = data.get('teams', [])
    players = data.setdefault('players', [])
    entries = {p['original_id']: p for p in players if p.get('original_id') is not None}

    def entry(pid):
        if pid not in entries:
            entries[pid] = load_player(pid)
            players.append(entries[pid])
        return entries[pid]

    def leave(pid, team, heir):
        """pid leaves team; heir (the joining player's ref) takes his captaincy, set pieces and lineup places in the
        team's entry, as the app does when someone takes a place."""
        e = entry(pid)
        e['teams'] = [lk for lk in e.get('teams', []) if lk.get('team') != team]
        swap = lambda ref: heir if ref == pid else ref  # noqa: E731
        for tm in teams:
            if (tm.get('original_id') if tm.get('original_id') is not None else tm.get('uid')) != team:
                continue
            if 'captain' in tm:
                tm['captain'] = swap(tm['captain'])
            tm['takers'] = {role: swap(ref) for role, ref in (tm.get('takers') or {}).items()}
            for lu in tm.get('lineups') or []:
                lu['starters'] = [swap(ref) for ref in lu.get('starters', [])]
                lu['reserves'] = [swap(ref) for ref in lu.get('reserves', [])]

    changed = False
    for p in list(players):
        for lk in p.get('teams', []):
            if lk.get('replaces') is not None:
                heir = p['original_id'] if p.get('original_id') is not None else p['uid']
                leave(lk.pop('replaces'), lk['team'], heir)
                changed = True
            lk.pop('replaces', None)
    for tm in teams:
        key = tm.get('original_id') if tm.get('original_id') is not None else tm.get('uid')
        for gp in tm.pop('game_players', []) or []:
            changed = True
            if gp.get('replaces') is not None:
                leave(gp['replaces'], key, gp['player_id'])
            e = entry(gp['player_id'])
            if not any(lk.get('team') == key for lk in e.get('teams', [])):
                e.setdefault('teams', []).append({'team': key, 'number': gp.get('number'), 'position': gp.get('position')})
    return changed
