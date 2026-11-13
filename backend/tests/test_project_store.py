"""Project folder housekeeping on save (fsapi.project_store)."""
import os

from fsapi import project_store
from fsapi.project_store import ProjectStore
from fsmod import model


def kit_with_font(path):
    real = model.RealKit(number_font='kit', number_font_file=path)
    return model.Project(teams=[model.Team(uid='t1', name='T', primary_color=(1, 2, 3), secondary_color=(4, 5, 6),
                                           use_real_kits=True, real_kits={'home': real})])


def test_save_survives_files_busy_for_a_moment(tmp_path, monkeypatch):
    """A file another process has open (the preview reading a font just imported, an antivirus) does not make the
    save fail: replacing waits for it, and a leftover that stays busy is deleted by a later save."""
    monkeypatch.setattr(project_store, 'BUSY_WAIT', 0.01)
    store = ProjectStore(str(tmp_path))
    upload = store.save_font_file('n.rx3', b'RX3b numbers')
    project = kit_with_font(upload)

    calls = {'replace': 0}
    real_replace, real_remove = os.replace, os.remove

    def busy_replace(source, target):  # the fixed name is busy twice, then free
        calls['replace'] += 1
        if calls['replace'] <= 2:
            raise PermissionError('busy')
        return real_replace(source, target)

    def busy_remove(path):  # the old upload stays busy
        if 'upload-' in path:
            raise PermissionError('busy')
        return real_remove(path)

    monkeypatch.setattr(project_store.os, 'replace', busy_replace)
    monkeypatch.setattr(project_store.os, 'remove', busy_remove)
    store.save(project)
    fixed = project.teams[0].real_kits['home'].number_font_file
    assert fixed == 'fonts/font-t1-home-numbers.rx3'
    assert os.path.isfile(os.path.join(tmp_path, 'fonts', 'font-t1-home-numbers.rx3'))
    assert os.path.isfile(os.path.join(tmp_path, *upload.split('/')))  # still busy: kept for now

    monkeypatch.setattr(project_store.os, 'replace', real_replace)
    monkeypatch.setattr(project_store.os, 'remove', real_remove)
    store.save(project)  # free now: the leftover goes
    assert sorted(os.listdir(os.path.join(tmp_path, 'fonts'))) == ['font-t1-home-numbers.rx3']
