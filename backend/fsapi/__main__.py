"""python -m fsapi [--port 8765] [--no-browser] [--parent-pid PID]"""
import argparse
import ctypes
import logging
import os
import threading
import webbrowser

import uvicorn

from . import diagnostics

log = logging.getLogger('fsapi')


def warm_up(app):
    """Loads the catalog (original database, slots...) in the background so the first page is fast."""
    from fastapi import HTTPException
    try:
        app.state.fsmod.catalog()
    except HTTPException:  # missing original files: the UI shows the setup screen
        pass
    except Exception:  # the UI shows it too (GET /api/catalog), but the cause goes to the log right away
        log.exception('loading the original game data failed')


def exit_with_parent(pid):
    """Desktop app: the backend ends when the window process ends, even if it crashed and could not stop us."""
    SYNCHRONIZE = 0x00100000
    INFINITE = 0xFFFFFFFF
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        os._exit(0)  # already gone

    def wait():
        ctypes.windll.kernel32.WaitForSingleObject(handle, INFINITE)
        os._exit(0)
    threading.Thread(target=wait, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--parent-pid', type=int)
    args = ap.parse_args()
    diagnostics.setup_logging()
    for line in diagnostics.environment_lines():  # first lines of the log: the user's machine
        log.info('ENV: %s', line)
    if args.parent_pid:
        exit_with_parent(args.parent_pid)
    try:
        from .main import app  # creating it reads the settings and upgrades the project: errors go to the log
    except Exception:
        log.exception('the backend could not start')
        raise
    url = f'http://localhost:{args.port}'
    threading.Thread(target=warm_up, args=(app,), daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_config=diagnostics.LOG_CONFIG)


if __name__ == '__main__':
    main()
