"""Entry point of the packaged backend (PyInstaller, desktop app): same as python -m fsapi."""
import multiprocessing

from fsapi.__main__ import main

if __name__ == '__main__':
    multiprocessing.freeze_support()  # the build's worker processes (fsmod.workers) start this executable again
    main()
