# FS4 Patch Studio

Desktop-style web app to create leagues, teams and players for **FIFA Street (2012)** running on the
[ReStreet](https://github.com/samuelit0davila/fifa-street-pc-port) PC port (2.x). It builds a patch from the game's own files: new leagues with their
flag, teams with crest and kits (generated or real FIFA 14-16 kits), players with photo, attributes, skills,
appearance and real scanned faces from FIFA 14 face packs, starting lineups per game mode, hiding or locking the
game's original leagues and teams, and optional patches to the game itself (e.g. keeping the close-up face at any
camera distance). A 3D preview shows each player as the game will draw them.

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

## Known issues

Real faces (FIFA 14-16 face packs):

- **Eyes in the 3D preview:** some faces in the FIFA 14 format show one white eye (no iris) or a missing eye in the
  preview. This is a preview problem only: **in game the eyes look right**.
- **Seen from far away the face changes a lot**, and on some faces the ear shows a bit of the teeth texture. The game
  draws distant players with a generic low-detail head whose texture layout differs from the FIFA 14-16 one. Close-up
  shots (replays, menus) look right. **Fix:** turn on "Close-up face at any distance" in the Patches screen.
- **Blond and red hair comes out dark**, in game and in the preview: the game draws scanned hair with a fixed grey
  tint over the pack's dark hair texture.
- **Short hair close to the scalp** can show dark stripes or patches on the forehead or the top of the head on some
  faces.
- The face converter has been checked in game with only a few faces: some packs, long or tied hair and other
  variations may still look wrong. Reports with a screenshot are very welcome.

Other:

- **Building is slow with very large crest images** (e.g. 3840×3840): each team takes a few seconds more. Images of
  about 1024 px look the same in game and build much faster.
- The 3D preview does not show the **body type**, nor the extra colored artwork some street tops get in game (sponsor
  logos and drawings; the kit brand symbol is shown).
- **Real kits** built from the Kits tab are not confirmed in game through the app yet (the kit files themselves were
  validated with test patches).

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
