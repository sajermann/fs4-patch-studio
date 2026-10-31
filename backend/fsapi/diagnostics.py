"""What a bug report needs: the log format, the user's machine and the support report (Settings > "Copy report").

The desktop app sends the backend's output to <data>/logs/backend.log and keeps the run before as backend.prev.log
(desktop/src-tauri/src/main.rs); errors of the interface reach the same log through POST /api/log.
"""
import logging
import logging.config
import os
import platform
import sys
from collections import deque

from . import settings

log = logging.getLogger('fsapi')

LOG_FILES = ('backend.log', 'backend.prev.log', 'desktop.log')
REPORT_TAIL_LINES = 400  # last lines of each log file in the report

# uvicorn's logging with the time on every line (the default has none) and the app's own logger ('fsapi')
LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {'()': 'uvicorn.logging.DefaultFormatter', 'use_colors': False,
                    'fmt': '%(asctime)s %(levelprefix)s %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S'},
        'access': {'()': 'uvicorn.logging.AccessFormatter', 'use_colors': False,
                   'fmt': '%(asctime)s %(levelprefix)s "%(request_line)s" %(status_code)s',
                   'datefmt': '%Y-%m-%d %H:%M:%S'},
    },
    'handlers': {
        'default': {'formatter': 'default', 'class': 'logging.StreamHandler', 'stream': 'ext://sys.stderr'},
        'access': {'formatter': 'access', 'class': 'logging.StreamHandler', 'stream': 'ext://sys.stdout'},
    },
    'loggers': {
        'uvicorn': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
        'uvicorn.error': {'level': 'INFO'},
        'uvicorn.access': {'handlers': ['access'], 'level': 'INFO', 'propagate': False},
        'fsapi': {'handlers': ['default'], 'level': 'INFO', 'propagate': False},
    },
}


def setup_logging():
    """Before the app is created: errors while it starts (settings, project upgrade) already have the format."""
    logging.config.dictConfig(LOG_CONFIG)


def environment_lines():
    win = sys.getwindowsversion() if sys.platform == 'win32' else None
    return [
        f'app version: {os.environ.get("FSMOD_APP_VERSION") or "(not set: development)"}',
        f'os: {platform.platform()} | {platform.machine()}'
        + (f' | build {win.build}, service pack "{win.service_pack}"' if win else ''),
        f'python: {platform.python_version()} | packaged: {settings.FROZEN}',
        f'data folder: {settings.DATA_DIR}',
    ]


def log_files():
    """Log files of the desktop app that exist (none in development, where the log is the console)."""
    return [os.path.join(settings.LOG_DIR, name) for name in LOG_FILES
            if os.path.isfile(os.path.join(settings.LOG_DIR, name))]


def _tail(path, lines=REPORT_TAIL_LINES):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return ''.join(deque(f, maxlen=lines))
    except OSError as e:
        return f'(could not read: {e})\n'


def report(sections):
    """Plain-text support report: the machine, `sections` ({title: lines}, from the app's state) and the end of
    every log file."""
    out = ['FS4 Patch Studio - support report', '']
    for title, lines in {'environment': environment_lines(), **sections}.items():
        out.append(f'== {title}')
        out.extend(f'  {line}' for line in lines)
        out.append('')
    files = log_files()
    if not files:
        out.append('(no log files: development runs log to the console)')
    for path in files:
        out.append(f'== {os.path.basename(path)} (last {REPORT_TAIL_LINES} lines)')
        out.append(_tail(path).rstrip('\n'))
        out.append('')
    return '\n'.join(out) + '\n'
