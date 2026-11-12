"""The notification center: every message the interface showed in a toast (errors, successes, warnings, infos) kept
in notifications.json next to config.json, so they survive closing the app.

It is a user file like config.json: a newer version of the app opens the files of older versions. Every field added
later must be optional (with a default) and FORMAT_VERSION goes up when the shape changes; a file that cannot be read
is kept aside as notifications.broken-<time>.json and the list starts empty instead of the app not starting."""
import datetime
import json
import logging
import os
import threading
import time
from typing import Literal, Optional

from pydantic import BaseModel, Field

log = logging.getLogger('fsapi')

FORMAT_VERSION = 1
KINDS = ('error', 'warning', 'success', 'info')
Kind = Literal['error', 'warning', 'success', 'info']
ReadState = Literal['all', 'read', 'unread']


class Notification(BaseModel):
    id: int
    kind: Kind = 'info'
    title: str = ''
    description: Optional[str] = None
    created_at: str  # ISO 8601 with the time zone (when it was shown, not when it reached the backend)
    read: bool = False
    language: Optional[str] = None  # interface language it was written in ('pt-BR', 'en')
    entity: Optional[str] = None  # uid of the league/team/player it is about: the UI links to it


class NotificationFile(BaseModel):
    version: int = FORMAT_VERSION
    next_id: int = 1
    items: list[Notification] = Field(default_factory=list)  # oldest first (appending is cheap)


class NewNotification(BaseModel):
    kind: Kind = 'info'
    title: str = Field('', max_length=2000)
    description: Optional[str] = Field(None, max_length=20000)
    created_at: Optional[str] = None  # sent by the UI when it queued the notification while the backend was down
    language: Optional[str] = None
    entity: Optional[str] = None


class Selection(BaseModel):
    """Which notifications an action applies to: the given ids, or (all=True) every one matching the filters
    except the excluded ids ("select all, on every page" in the list)."""
    ids: list[int] = Field(default_factory=list)
    all: bool = False
    kind: Optional[Kind] = None
    state: ReadState = 'all'
    exclude: list[int] = Field(default_factory=list)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


class NotificationStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = None  # loaded on first use

    # ------------------------------------------------------------------ file
    def _load(self):
        if self._data is not None:
            return self._data
        data = NotificationFile()
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding='utf-8') as f:
                    data = NotificationFile.model_validate(json.load(f))
            except (ValueError, UnicodeError) as e:
                kept = f'{os.path.splitext(self.path)[0]}.broken-{time.strftime("%Y%m%d-%H%M%S")}.json'
                os.replace(self.path, kept)
                log.error('notifications file %s could not be read (%s: %s); kept as %s, starting empty',
                          self.path, type(e).__name__, e, kept)
                data = NotificationFile()
        if data.items:
            data.next_id = max(data.next_id, max(n.id for n in data.items) + 1)
        data.version = FORMAT_VERSION  # an older file is written back in the current format on the next change
        self._data = data
        return data

    def _save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self._data.model_dump(mode='json', exclude_none=True), f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ queries
    @staticmethod
    def _matches(n, kind, state):
        return ((kind is None or n.kind == kind)
                and (state == 'all' or (state == 'read') == n.read))

    def _selected(self, data, sel: Selection):
        if sel.all:
            exclude = set(sel.exclude)
            return [n for n in data.items if self._matches(n, sel.kind, sel.state) and n.id not in exclude]
        ids = set(sel.ids)
        return [n for n in data.items if n.id in ids]

    def unread_count(self):
        with self._lock:
            return sum(1 for n in self._load().items if not n.read)

    def page(self, offset=0, limit=50, kind=None, state='all'):
        """Newest first: {total (matching the filters), unread (all of them), items}."""
        with self._lock:
            data = self._load()
            found = [n for n in reversed(data.items) if self._matches(n, kind, state)]
            return {'total': len(found), 'unread': sum(1 for n in data.items if not n.read),
                    'items': [n.model_dump(mode='json') for n in found[offset:offset + limit]]}

    def get(self, nid):
        with self._lock:
            return next((n.model_dump(mode='json') for n in self._load().items if n.id == nid), None)

    # ------------------------------------------------------------------ changes
    def add(self, new: NewNotification, language=None):
        with self._lock:
            data = self._load()
            n = Notification(id=data.next_id, kind=new.kind, title=new.title, description=new.description or None,
                             created_at=new.created_at or now_iso(), language=new.language or language,
                             entity=new.entity or None)
            data.next_id += 1
            data.items.append(n)
            self._save()
            return n.model_dump(mode='json')

    def mark(self, sel: Selection, read: bool):
        """Marks the selection read (or unread again); returns how many changed."""
        with self._lock:
            data = self._load()
            changed = 0
            for n in self._selected(data, sel):
                if n.read != read:
                    n.read = read
                    changed += 1
            if changed:
                self._save()
            return changed

    def delete(self, sel: Selection):
        with self._lock:
            data = self._load()
            gone = {n.id for n in self._selected(data, sel)}
            if gone:
                data.items = [n for n in data.items if n.id not in gone]
                self._save()
            return len(gone)
