"""Paths and the local user configuration (backend/config.json, not in git)."""
import json
import logging
import os
import sys
import time
from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

log = logging.getLogger('fsapi')

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(BACKEND_DIR)
REPO_DIR = os.path.dirname(APP_DIR)
CORE_DIR = os.path.join(APP_DIR, 'core')
FROZEN = getattr(sys, 'frozen', False)  # packaged backend (PyInstaller, desktop app): files next to the executable
FRONTEND_DIST = (os.path.join(sys._MEIPASS, 'frontend_dist') if FROZEN
                 else os.path.join(APP_DIR, 'frontend', 'dist'))
# the app's own data (config, project, ...): the backend folder in development; the desktop app always sets it
DATA_DIR = os.environ.get('FSMOD_DATA_DIR') or (
    os.path.join(os.path.dirname(sys.executable), 'data') if FROZEN else BACKEND_DIR)
if FROZEN:
    os.environ['FSMOD_DATA_DIR'] = DATA_DIR  # fsmod.game derives original_files/patch from it
CONFIG_PATH = os.environ.get('FSMOD_CONFIG', os.path.join(DATA_DIR, 'config.json'))
# written by the desktop app (backend.log = the backend's output, backend.prev.log = the run before, desktop.log);
# in development the backend logs to the console only
LOG_DIR = os.path.join(DATA_DIR, 'logs')
DEFAULT_PROJECT_DIR = os.path.join(DATA_DIR, 'project')
LEGACY_PROJECT_DIR = os.path.join(REPO_DIR, 'projeto')  # default before 24/10/2026; moved on start

if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from fsmod import workers  # noqa: E402 (after the core folder is on the path)


Language = Literal['pt-BR', 'en']


class Config(BaseModel):
    game_dir: Optional[str] = None  # game root (the folder that holds Game; ReStreet 2.x layout)
    save_dir: Optional[str] = None  # profile folder of the save (<Documents>\fifastreet\<profile>\4541097B)
    project_dir: str = DEFAULT_PROJECT_DIR
    backups_dir: str = os.path.join(DATA_DIR, 'backups')
    # FIFA 14-16 face pack folders, set in the settings (read in place, never written); one pack per folder. Until
    # 12/11/2026 there was a single `face_pack_dir`: it becomes the only item of the list (_one_face_pack_dir)
    face_pack_dirs: list[str] = []
    players_base_file: Optional[str] = None  # players JSON (fsapi.ea_players contract), read in place, never written
    terms_version: Optional[int] = None  # version of the first-run notice the user accepted (game_setup.TERMS_VERSION)
    # how much of the machine a build may use (fsmod.workers.plan): None = the defaults (all cores but one, 50% of the
    # memory); added 11/11/2026, optional so older config files load unchanged. Out-of-range values (more cores than
    # the machine has, memory outside 10-90%) are brought into range instead of refused: a refused file would make
    # the app start with the defaults of every setting
    build_cores: Optional[int] = None
    build_memory_percent: Optional[int] = None
    # interface language (added 12/11/2026, optional: older files load unchanged); new notifications are written in it.
    # A value this version does not know (written by a newer one) is dropped instead of refusing the whole file
    language: Optional[Language] = None

    @model_validator(mode='before')
    @classmethod
    def _one_face_pack_dir(cls, data):
        if isinstance(data, dict) and 'face_pack_dir' in data:
            data = dict(data)
            old = data.pop('face_pack_dir')
            if 'face_pack_dirs' not in data:
                data['face_pack_dirs'] = [old] if isinstance(old, str) and old.strip() else []
        return data

    @field_validator('face_pack_dirs', mode='after')
    @classmethod
    def _clean_face_pack_dirs(cls, v):
        """Trimmed, without empty items or repeated folders (same folder in another case / with a trailing slash)."""
        out, seen = [], set()
        for folder in v:
            folder = folder.strip()
            key = os.path.normcase(os.path.normpath(folder)) if folder else None
            if key and key not in seen:
                seen.add(key)
                out.append(folder)
        return out

    @field_validator('language', mode='before')
    @classmethod
    def _known_language(cls, v):
        return v if v in ('pt-BR', 'en') else None

    @field_validator('build_cores', mode='after')
    @classmethod
    def _cores_in_range(cls, v):
        return workers.clamp_cores(v)

    @field_validator('build_memory_percent', mode='after')
    @classmethod
    def _memory_in_range(cls, v):
        return workers.clamp_memory_percent(v)


def load_config(path=None):
    """The saved settings; a file that cannot be read (broken JSON, unknown shape) is kept aside as
    config.broken-<time>.json and the app starts with the defaults (the setup screen asks again) instead of not
    starting at all."""
    path = path or CONFIG_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                config = Config.model_validate(json.load(f))
        except (ValueError, UnicodeError) as e:  # json.JSONDecodeError and pydantic.ValidationError are ValueErrors
            kept = f'{os.path.splitext(path)[0]}.broken-{time.strftime("%Y%m%d-%H%M%S")}.json'
            os.replace(path, kept)
            log.error('settings file %s could not be read (%s: %s); kept as %s, starting with the defaults',
                      path, type(e).__name__, e, kept)
            return Config()
        if os.path.normcase(os.path.abspath(config.project_dir)) == os.path.normcase(LEGACY_PROJECT_DIR):
            config.project_dir = DEFAULT_PROJECT_DIR  # old default: the project moves with it (AppState)
        return config
    return Config()


def save_config(config, path=None):
    path = path or CONFIG_PATH
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
