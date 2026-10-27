"""Windows dialogs opened by the backend, which runs on the user's machine: the browser cannot see folder paths
nor save a 2 GB file where the user wants. tkinter ships with Python; each dialog lives and dies in its own thread,
topmost so it does not open behind the browser. None when cancelled."""
import os
import threading


def _run(ask):
    result = {}

    def run():
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            result['path'] = ask(root)
        finally:
            root.destroy()
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    path = result.get('path')
    return os.path.normpath(path) if path else None


def browse_folder(initial=None, title='Escolha a pasta'):
    from tkinter import filedialog
    return _run(lambda root: filedialog.askdirectory(
        parent=root, initialdir=initial if initial and os.path.isdir(initial) else None, title=title, mustexist=True))


def open_file(initial=None, title='Escolha o arquivo', extension='.json', kind='Arquivo JSON'):
    from tkinter import filedialog
    folder = os.path.dirname(initial) if initial else None
    return _run(lambda root: filedialog.askopenfilename(
        parent=root, initialdir=folder if folder and os.path.isdir(folder) else None, title=title,
        filetypes=[(kind, f'*{extension}')]))


def save_file(default_name, title='Salvar como', extension='.zip', kind='Arquivo zip'):
    from tkinter import filedialog
    return _run(lambda root: filedialog.asksaveasfilename(
        parent=root, initialfile=default_name, defaultextension=extension, title=title,
        filetypes=[(kind, f'*{extension}')]))
