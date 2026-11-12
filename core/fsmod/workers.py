"""How much of the machine a build may use, and a process pool that never breaks the build.

The real-face conversion (fsmod.scanface) is pure Python: threads do not run it in parallel (the GIL), so the build
runs it in worker processes. How many: the user's limits (settings: cores, percent of the memory), and always the
defensive answer when the machine does not tell:
  - cores the process may use (os.process_cpu_count / affinity / os.cpu_count); unknown -> 1;
  - total memory (Windows GlobalMemoryStatusEx, POSIX sysconf); unknown -> 1 worker;
  - default cores: all but one (so the PC stays usable); default memory: 50%; never less than 1 worker.
The pool (Pool) falls back to running in the calling process when worker processes cannot start or die (antivirus,
packaged app, out of memory): slower, same result.
"""
import concurrent.futures
import ctypes
import logging
import multiprocessing
import os
import sys

log = logging.getLogger('fsmod')

DEFAULT_MEMORY_PERCENT = 50
MEMORY_PERCENT_RANGE = (10, 90)  # the user's setting; never all the memory (the system and the app need some)
WORKER_MEMORY_MB = 300  # budget per face worker (measured peak ~80 MB with the standard and sharp hair, 11/11/2026)


def cpu_cores():
    """Cores this process may use, or None when the system does not tell."""
    for probe in (getattr(os, 'process_cpu_count', None),
                  lambda: len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                  os.cpu_count):
        try:
            n = probe() if probe else None
        except (OSError, ValueError, NotImplementedError):
            n = None
        if isinstance(n, int) and n >= 1:
            return n
    return None


def total_memory():
    """Physical memory of the machine in bytes, or None when the system does not tell."""
    try:
        if sys.platform == 'win32':
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong),
                            ('available', ctypes.c_ulonglong), ('total_page', ctypes.c_ulonglong),
                            ('available_page', ctypes.c_ulonglong), ('total_virtual', ctypes.c_ulonglong),
                            ('available_virtual', ctypes.c_ulonglong), ('available_extended', ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) and status.total > 0:
                return int(status.total)
            return None
        pages, size = os.sysconf('SC_PHYS_PAGES'), os.sysconf('SC_PAGE_SIZE')
        return pages * size if pages > 0 and size > 0 else None
    except (AttributeError, OSError, ValueError):
        return None


def default_cores(cores=None):
    """All cores but one (1 when unknown or when there is only one)."""
    cores = cpu_cores() if cores is None else cores
    return max(1, (cores or 1) - 1)


def plan(cores=None, memory_percent=None, machine_cores=None, machine_memory=None):
    """Number of worker processes for the build. cores / memory_percent: the user's settings (None = defaults);
    machine_cores / machine_memory: for tests (None = read from the system). Always at least 1."""
    available = cpu_cores() if machine_cores is None else machine_cores
    if not available:
        return 1
    wanted = default_cores(available) if cores is None else max(1, min(int(cores), available))
    memory = total_memory() if machine_memory is None else machine_memory
    if not memory:
        return 1
    percent = DEFAULT_MEMORY_PERCENT if memory_percent is None else clamp_memory_percent(memory_percent)
    fits = int(memory * percent / 100 // (WORKER_MEMORY_MB * 2 ** 20))
    return max(1, min(wanted, fits))


def clamp_cores(cores, machine_cores=None):
    """The user's cores setting kept between 1 and the machine's cores (None stays None = the default)."""
    if cores is None:
        return None
    available = cpu_cores() if machine_cores is None else machine_cores
    return max(1, min(int(cores), available or 1))


def clamp_memory_percent(percent):
    """The user's memory setting kept in MEMORY_PERCENT_RANGE (None stays None = the default)."""
    if percent is None:
        return None
    return max(MEMORY_PERCENT_RANGE[0], min(int(percent), MEMORY_PERCENT_RANGE[1]))


def describe(cores=None, memory_percent=None):
    """Facts for the settings screen and the log."""
    machine_cores, memory = cpu_cores(), total_memory()
    return {'cores': machine_cores, 'memory_mb': memory // 2 ** 20 if memory else None,
            'default_cores': default_cores(machine_cores) if machine_cores else 1,
            'default_memory_percent': DEFAULT_MEMORY_PERCENT, 'memory_percent_range': list(MEMORY_PERCENT_RANGE),
            'worker_memory_mb': WORKER_MEMORY_MB,
            'workers': plan(cores, memory_percent)}


class Task:
    """Result of one call given to Pool.submit: result() runs it in this process if its worker failed."""

    def __init__(self, pool, fn, args, future=None):
        self.pool, self.fn, self.args, self.future = pool, fn, args, future
        self.done, self.value = False, None

    def result(self):
        if not self.done:
            value = None
            if self.future is not None:
                try:
                    value = self.future.result()
                except concurrent.futures.process.BrokenProcessPool as e:
                    self.pool.broken(e)
                    self.future = None
            if self.future is None:
                value = self.fn(*self.args)
            self.value, self.done = value, True
        return self.value


class Pool:
    """Process pool of `workers` processes (1 = everything in this process). initializer(*initargs) runs once in
    every worker; local_initializer(*initargs) (default: initializer) once in this process before a call runs here. Exceptions of the calls go to result() as usual; a pool
    that cannot start or breaks is closed and the remaining calls run here (log warning)."""

    def __init__(self, workers, initializer=None, initargs=(), log_fn=None, local_initializer=None):
        self.workers, self.initializer, self.initargs = workers, initializer, initargs
        self.local_initializer = local_initializer or initializer
        self.log = log_fn or log.warning
        self.executor, self.local_ready = None, False
        if workers > 1:
            try:
                self.executor = concurrent.futures.ProcessPoolExecutor(
                    max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                    initializer=initializer, initargs=initargs)
            except (OSError, ValueError, RuntimeError) as e:
                self.log(f'worker processes unavailable ({type(e).__name__}: {e}); running in a single process')

    def broken(self, error):
        if self.executor is not None:
            self.log(f'worker processes unavailable ({type(error).__name__}: {error}); running in a single process')
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None

    def _local(self, fn, *args):
        if not self.local_ready and self.local_initializer:
            self.local_initializer(*self.initargs)
        self.local_ready = True
        return fn(*args)

    def submit(self, fn, *args):
        if self.executor is not None:
            try:
                return Task(self, self._local, (fn, *args), self.executor.submit(fn, *args))
            except (concurrent.futures.process.BrokenProcessPool, RuntimeError, OSError) as e:
                self.broken(e)
        return Task(self, self._local, (fn, *args))

    def shutdown(self):
        if self.executor is not None:
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.executor = None
