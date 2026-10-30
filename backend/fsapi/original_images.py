"""Images of the original teams and players shown in the app's lists: the menu crest and the menu photo (both
128 px), read from the originals on first use and kept as WebP files in a disk cache, so each one is converted once.

The cache lives in <data dir>/cache/originals/<key>/ (crests/<teamid>.webp, photos/<playerid>.webp); the key comes
from the size and date of the files read, so importing other originals starts a new folder and the old ones go away.
"""
import hashlib
import io
import os
import shutil
import uuid
from functools import cached_property

from fsmod import crest, leaguelogo, photo
from fsmod.game import GAME_DATA, PHOTOS_FILE

SOURCES = ('data1.big', PHOTOS_FILE)  # menu crests, player photos
WEBP_QUALITY = 90


class OriginalImages:
    def __init__(self, game, cache_root):
        self.game = game
        self.root = os.path.join(cache_root, 'originals')

    @cached_property
    def folder(self):
        """This originals' cache folder; cache folders of other originals are removed."""
        h = hashlib.sha1()
        for rel in SOURCES:
            st = os.stat(os.path.join(self.game.folder, GAME_DATA, rel))
            h.update(f'{rel}:{st.st_size}:{st.st_mtime_ns};'.encode())
        key = h.hexdigest()[:16]
        if os.path.isdir(self.root):
            for name in os.listdir(self.root):
                if name != key:
                    shutil.rmtree(os.path.join(self.root, name), ignore_errors=True)
        return os.path.join(self.root, key)

    def has_crest(self, teamid):
        return self.game.locate(crest.ui_crest_name('medium', teamid)) is not None

    def has_photo(self, playerid):
        return playerid in self.game.photo_index

    def crest(self, teamid):
        """WebP bytes of the team's menu crest, or None (the game's internal teams have none)."""
        return self._cached('crests', teamid, lambda: crest.original_crest(self.game, teamid))

    def photo(self, playerid):
        """WebP bytes of the player's menu photo, or None (most generic-head players have none)."""
        return self._cached('photos', playerid, lambda: photo.original_photo(self.game, playerid))

    def league_flag(self, countryid):
        """WebP bytes of the square flag of a league's country (the league image in the selector), or None."""
        def load():
            entry = self.game.read_entry(leaguelogo.asset_name('flag_small', countryid))
            return leaguelogo.read_image(entry[2])[0] if entry else None
        return self._cached('flags', countryid, load)

    def _cached(self, kind, item_id, load):
        path = os.path.join(self.folder, kind, f'{item_id}.webp')
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                return f.read()
        img = load()
        if img is None:
            return None
        buf = io.BytesIO()
        img.convert('RGBA').save(buf, format='WEBP', quality=WEBP_QUALITY)
        data = buf.getvalue()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f'{path}.{uuid.uuid4().hex}.tmp'  # requests run in parallel threads: write whole, then rename
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
        return data
