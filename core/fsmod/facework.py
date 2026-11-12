"""Real-face conversion run in the build's worker processes (fsmod.workers.Pool; called by fsmod.builder).

Kept apart from fsmod.builder so a worker process only imports what the conversion needs. init() runs once per
worker: it keeps the face templates (read from the original files by the main process) and lowers the worker's
priority, so a build never makes the rest of the PC slow.
"""
import os
import sys

from . import chunk, scanface

_templates = None


def init(templates):
    global _templates
    _templates = templates
    try:
        if sys.platform == 'win32':
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        elif hasattr(os, 'nice'):
            os.nice(5)
    except (AttributeError, OSError):
        pass


def init_here(templates):
    """init() for the calling process itself (fallback without workers): keeps its priority."""
    global _templates
    _templates = templates


def convert(files, player_id, hair_color, paint, hair_mode, hair_thickness):
    """{loose file name: bytes} of a real face converted for player_id (scanface.convert + chunkzip)."""
    converted = scanface.convert(_templates, files, player_id, hair_color, paint=paint, hair_mode=hair_mode,
                                 hair_thickness=hair_thickness)
    return {scanface.ASSETS + name: chunk.chunkzip(data) for name, data in converted.items()}
