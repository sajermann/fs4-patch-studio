# PyInstaller spec of the packaged backend used by the desktop app (desktop/).
# Build from backend/ (after npm run build in frontend/):  python -m PyInstaller --noconfirm fs4-backend.spec
# Output: backend/dist/fs4-backend/ (fs4-backend.exe + _internal/), bundled by Tauri as a resource.
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['run_backend.py'],
    pathex=['.', '../core'],
    datas=[
        ('../core/fsmod/bin/lzxdec.exe', 'fsmod/bin'),
        ('../frontend/dist', 'frontend_dist'),
    ],
    # uvicorn picks its loop/protocol implementations by name at runtime
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('fsmod') + collect_submodules('fsapi'),
    excludes=['pytest', 'httpx'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='fs4-backend',
    console=True,  # started hidden by the desktop app; its output goes to the log file
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='fs4-backend', upx=False)
