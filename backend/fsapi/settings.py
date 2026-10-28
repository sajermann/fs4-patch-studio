"""Paths and the local user configuration (backend/config.json, not in git)."""
import json
import os
import sys
from typing import Optional

from pydantic import BaseModel

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
DEFAULT_PROJECT_DIR = os.path.join(DATA_DIR, 'project')
LEGACY_PROJECT_DIR = os.path.join(REPO_DIR, 'projeto')  # default before 24/10/2026; moved on start

if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)


class Config(BaseModel):
    game_dir: Optional[str] = None  # game root (the folder that holds Game; ReStreet 2.x layout)
    save_dir: Optional[str] = None  # profile folder of the save (<Documents>\fifastreet\<profile>\4541097B)
    project_dir: str = DEFAULT_PROJECT_DIR
    backups_dir: str = os.path.join(DATA_DIR, 'backups')
    face_pack_dir: Optional[str] = None  # FIFA 14 face pack folder, set in the settings (read in place, never written)
    players_base_file: Optional[str] = None  # players JSON (fsapi.ea_players contract), read in place, never written
    terms_version: Optional[int] = None  # version of the first-run notice the user accepted (game_setup.TERMS_VERSION)


def load_config(path=None):
    path = path or CONFIG_PATH
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            config = Config.model_validate(json.load(f))
        if os.path.normcase(os.path.abspath(config.project_dir)) == os.path.normcase(LEGACY_PROJECT_DIR):
            config.project_dir = DEFAULT_PROJECT_DIR  # old default: the project moves with it (AppState)
        return config
    return Config()


def save_config(config, path=None):
    path = path or CONFIG_PATH
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
