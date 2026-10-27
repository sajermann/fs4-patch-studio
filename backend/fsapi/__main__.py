"""python -m fsapi [--port 8765] [--no-browser]"""
import argparse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()
    url = f'http://localhost:{args.port}'
    threading.Thread(target=warm_up, daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
