"""python -m fsapi [--port 8765] [--no-browser] [--parent-pid PID]"""
import argparse
import ctypes
import os
import threading
import webbrowser

import uvicorn

from .main import app


def warm_up():
    """Loads the catalog (original database, slots...) in the background so the first page is fast."""
    try:
        app.state.fsmod.catalog()
    except Exception:  # missing original files: the UI shows the setup screen
        pass


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
    if args.parent_pid:
        exit_with_parent(args.parent_pid)
    url = f'http://localhost:{args.port}'
    threading.Thread(target=warm_up, daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
