import sys

import pytest

from fsapi import dialogs


def child(monkeypatch, code):
    """Makes the dialog's child process run `code` instead of showing a dialog."""
    monkeypatch.setattr(dialogs, '_command', lambda request: [sys.executable, '-c', code])


def test_picked_path_is_normalized(monkeypatch):
    child(monkeypatch, 'print("noise"); print(\'{"path": "C:/Games/Faces"}\')')
    assert dialogs.browse_folder() == r'C:\Games\Faces'


def test_cancelled_dialog_is_none(monkeypatch):
    child(monkeypatch, 'print(\'{"path": null}\')')
    assert dialogs.open_file() is None


def test_a_crashed_dialog_fails_only_the_request(monkeypatch):
    child(monkeypatch, 'import os, sys; sys.stderr.write("Tcl panic"); sys.stderr.flush(); os._exit(0xC0000005 & 0xFF)')
    with pytest.raises(dialogs.DialogError, match='folder dialog failed.*Tcl panic'):
        dialogs.browse_folder()


def test_an_error_inside_the_dialog_is_raised(monkeypatch):
    child(monkeypatch, 'print(\'{"error": "TclError: no display"}\')')
    with pytest.raises(dialogs.DialogError, match='save dialog failed: TclError: no display'):
        dialogs.save_file('patch.zip')


def test_child_entry_reports_errors_as_json(capsys):
    dialogs.run_child('not json')  # fails before any window: still a JSON answer
    assert capsys.readouterr().out.strip().startswith('{"error": ')
