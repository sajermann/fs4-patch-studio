"""Windows dialogs opened by the backend, which runs on the user's machine: the browser cannot see folder paths
nor save a 2 GB file where the user wants. tkinter ships with Python. None when cancelled; a dialog that fails raises.

Each dialog runs in a child process of its own (the backend itself with --dialog, see run_child), on that process's
main thread: a Tk dialog in a thread of the server crashed the whole packaged backend (access violation in ntdll with
Tcl/Tk 9, when the user used the dialog), and the app lost its server. A crash now only fails that one request."""
import json
import os
import subprocess
import sys

from . import settings

DIALOG_ARG = '--dialog'


class DialogError(RuntimeError):
    pass


def browse_folder(initial=None, title='Escolha a pasta'):
    return _run({'kind': 'folder', 'initial': initial, 'title': title})


def open_file(initial=None, title='Escolha o arquivo', extension='.json', kind='Arquivo JSON'):
    return _run({'kind': 'open', 'initial': initial, 'title': title, 'extension': extension, 'type': kind})


def save_file(default_name, title='Salvar como', extension='.zip', kind='Arquivo zip'):
    return _run({'kind': 'save', 'initial': default_name, 'title': title, 'extension': extension, 'type': kind})


def _command(request):
    payload = json.dumps(request)
    if settings.FROZEN:  # the packaged backend: its executable runs the dialog (fsapi.__main__)
        return [sys.executable, DIALOG_ARG, payload]
    return [sys.executable, '-m', 'fsapi', DIALOG_ARG, payload]


def _run(request):
    proc = subprocess.run(_command(request), cwd=settings.BACKEND_DIR, stdin=subprocess.DEVNULL,
                          capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    out = proc.stdout.decode('utf-8', 'replace').strip().splitlines()
    try:
        answer = json.loads(out[-1]) if out else None
    except ValueError:
        answer = None
    if proc.returncode != 0 or not isinstance(answer, dict):
        detail = proc.stderr.decode('utf-8', 'replace').strip()[-500:]
        raise DialogError(f'the {request["kind"]} dialog failed (exit code {proc.returncode & 0xFFFFFFFF:#x})'
                          + (f': {detail}' if detail else ''))
    if 'error' in answer:
        raise DialogError(f'the {request["kind"]} dialog failed: {answer["error"]}')
    path = answer.get('path')
    return os.path.normpath(path) if path else None


def _ask(request):
    """Shows the dialog on this thread (the child process's main thread); the path picked, or None."""
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes('-topmost', True)  # so it does not open behind the app's window
    try:
        kind, initial, title = request['kind'], request.get('initial'), request.get('title')
        if kind == 'folder':
            return filedialog.askdirectory(parent=root, title=title, mustexist=True,
                                           initialdir=initial if initial and os.path.isdir(initial) else None)
        filetypes = [(request['type'], f'*{request["extension"]}')]
        if kind == 'open':
            folder = os.path.dirname(initial) if initial else None
            return filedialog.askopenfilename(parent=root, title=title, filetypes=filetypes,
                                              initialdir=folder if folder and os.path.isdir(folder) else None)
        return filedialog.asksaveasfilename(parent=root, title=title, initialfile=initial, filetypes=filetypes,
                                            defaultextension=request['extension'])
    finally:
        root.destroy()


def run_child(payload):
    """Entry of the child process: prints {"path": ...} or {"error": ...} as the last line of its output."""
    try:
        answer = {'path': _ask(json.loads(payload)) or None}
    except Exception as e:  # noqa: BLE001 (the server raises it again in the request: the UI shows it)
        answer = {'error': f'{type(e).__name__}: {e}'}
    sys.stdout.write(json.dumps(answer) + '\n')
    sys.stdout.flush()
