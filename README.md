# FS4 Patch Studio

Desktop-style web app to create leagues, teams and players for **FIFA Street (2012)** running on the
[ReStreet](https://github.com/samuelit0davila/fifa-street-pc-port) PC port (2.x). It builds a patch from the game's own files: new leagues with their
flag, teams with crest and kits (generated or real FIFA 14-16 kits), players with photo, attributes, skills,
appearance and real scanned faces from FIFA 14 face packs, starting lineups per game mode, and hiding or locking the
game's original leagues and teams. A 3D preview shows each player as the game will draw them.

The interface is available in Portuguese (Brazil) and English, with light and dark themes.

> This project is not affiliated with or endorsed by EA, FIFA or the ReStreet authors. It ships **no game files**:
> you need your own copy of the game, and the app reads the originals from it.

## How it works

- The game database is the single source of truth: leagues, teams and players go into a new database archive
  (`data8.big`) that the game reads over the original one. The save file is never edited, so **every mod needs a new
  save** (the game only seeds a new save from the database).
- Everything is rebuilt from the untouched originals on every build, so the output never depends on what is
  installed.
- The app never writes to the game folder: it builds `backend/patch/Game/`, and you copy it over the game's `Game/`
  folder (keep a backup of the originals to remove the mod).

## Requirements

- Windows
- FIFA Street (2012) with ReStreet 2.x
- Python 3 (developed with 3.14) and Node.js (developed with 26)

## Running

```bat
start.bat
```

It installs the Python and npm dependencies on the first run, starts the backend on http://localhost:8765 and opens
the interface on http://localhost:5173. On the first run the setup screen asks for the game folder, checks that its
files are the official ones and imports them as the app's originals (see `backend/README.md` for the file list).

## Structure

| Folder | What it is |
|---|---|
| `core/fsmod/` | Python library: game database (T3DB), `.big` archives, textures, meshes, locale, crests, kits, photos, faces, 3D preview and the patch builder |
| `core/lzx/` | Source of `core/fsmod/bin/lzxdec.exe` (LZX decoder, libmspack) |
| `backend/fsapi/` | FastAPI server over `fsmod` (routes in `backend/README.md`) |
| `frontend/` | React + Vite + TypeScript + Tailwind + shadcn/ui (see `frontend/README.md`) |

Not in git (each user has their own): `backend/original_files/` (the game's originals), `backend/patch/` (build
output), `backend/project/` (your mod: `database.json`, images, faces), `backend/config.json` and `backend/cache/`.

## Tests

```bat
cd core && python -m pytest -q
cd backend && python -m pytest -q
```

Tests that need the game's original files (or other local data) are skipped when they are not available. The
backend tests use temporary folders and a fake game; they never touch a real installation.

## Contributing

The code is open, but **pull requests are not accepted for now**, to keep control of the project while it takes
shape. Suggestions are very welcome and questions will be answered as soon as possible: please use the
**[Discussions](../../discussions)** tab (Portuguese or English). See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[GNU GPL v3](LICENSE): you can use, study, change and share this program, but any distributed work based on it must
also be released under the GPL v3, with its source code. Under the additional terms in [NOTICE](NOTICE), it must also
credit this project with a link to this repository.

`core/lzx/` contains files of [libmspack](https://www.cabextract.org.uk/libmspack/) by Stuart Caie, licensed under
the [GNU LGPL 2.1](core/lzx/COPYING.LIB).
