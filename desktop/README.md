# Desktop app (Tauri)

Packaging only: development stays web (`start.bat`). The desktop app is a Tauri window that starts the packaged
backend (`backend/fs4-backend.spec`, PyInstaller) on a free local port and shows the interface it serves.

- **Data folder** (`FSMOD_DATA_DIR`): `data\` next to the executable, installed or portable (the installer puts the
  app in `%LOCALAPPDATA%\FS4 Patch Studio\`); if that folder is not writable, `%LOCALAPPDATA%\FS4 Patch Studio\data\`.
  Backend log: `<data>\logs\backend.log`.
- **Uninstall:** the installer's uninstaller offers to delete the data folder (unchecked by default) and first
  reminds the user to uninstall the game patch from the app.

## Build

Needs Node, Rust (MSVC toolchain + Visual Studio Build Tools) and Python with `backend/requirements-build.txt`:

```
python -m pip install -r backend/requirements-build.txt
./desktop/build.ps1            # or: ./desktop/build.ps1 -Python <path to python.exe>
```

Output in `desktop/release/`: the NSIS installer and the portable zip. GitHub Actions
(`.github/workflows/release.yml`) does the same on a `v*` tag and creates a draft release.
The version lives only in `src-tauri/tauri.conf.json` (the interface reads it too, through `vite.config.ts`). The
workflow refuses a tag that does not match it: `v0.2.0` ⇔ `"version": "0.2.0"` is a release; `v0.2.0-<suffix>`
(e.g. `v0.2.0-dev`) is a test build, published as a pre-release.
