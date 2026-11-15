"""What the backend is doing right now, for the opening screen (GET /api/startup).

Slow requests of the app's opening (the project, the game's data) say which phase they are in; the screen polls the
list while it waits, so the user sees the app working (and for how long) instead of a bare "loading". Phases are
codes (the UI has the texts) with optional numbers (params). Thread-safe: the requests run in FastAPI's thread pool.
"""
import contextlib
import threading
import time


class Activity:
    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}  # name -> {'phase', 'params', 'started_at', 'phase_started_at', 'count'}

    @contextlib.contextmanager
    def task(self, name):
        """with activity.task('project') as phase: phase('checking', players=10) ... Nested or concurrent uses of the
        same name share one entry (it ends when the last one does)."""
        now = time.time()
        with self._lock:
            entry = self._tasks.get(name)
            if entry is None:
                entry = self._tasks[name] = {'phase': None, 'params': {}, 'started_at': now,
                                             'phase_started_at': now, 'count': 0}
            entry['count'] += 1

        def phase(code, **params):
            with self._lock:
                entry.update(phase=code, params=params, phase_started_at=time.time())
        try:
            yield phase
        finally:
            with self._lock:
                entry['count'] -= 1
                if entry['count'] <= 0 and self._tasks.get(name) is entry:
                    del self._tasks[name]

    def snapshot(self):
        """{name: {'phase', 'params', 'elapsed', 'phase_elapsed'}} of what is running now."""
        now = time.time()
        with self._lock:
            return {name: {'phase': e['phase'], 'params': dict(e['params']),
                           'elapsed': round(now - e['started_at'], 1),
                           'phase_elapsed': round(now - e['phase_started_at'], 1)}
                    for name, e in self._tasks.items()}
