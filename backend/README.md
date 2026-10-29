# Backend

FastAPI server (`fsapi/`) over the core library (`core/fsmod`). Start it with `start.bat`
(installs the requirements if needed and opens http://localhost:8765), or `python -m fsapi` from this
folder. API docs: http://localhost:8765/docs. Tests: `python -m pytest -q`.

Local settings live in `config.json` (not in git; editable through `PUT /api/config`): `game_dir` (game
root of ReStreet 2.x, holds `Game`), `save_dir` (profile folder with `00000001`), `project_dir` (default
`project/` in the app data, i.e. this folder in development: `database.json` + `images/` + `faces/`; a project
in the old place, `<repo>/projeto/projeto.json`, is moved and renamed when the backend starts) and `backups_dir`.
The data folder can be changed with `FSMOD_DATA_DIR`.

## Development

Needs Python 3 (developed with 3.14) and Node.js (developed with 26). From the repository root:

```bat
start.bat
```

It installs the Python and npm dependencies on the first run, starts the backend on http://localhost:8765 and opens
the interface on http://localhost:5173. On the first run the setup screen asks for the game folder, checks that its
files are the official ones and imports them as the app's originals (see [original_files/](#original_files-not-in-git--provide-your-own)).
The installed/portable desktop app is packaged from the same code (see `desktop/README.md`).

| Folder | What it is |
|---|---|
| `core/fsmod/` | Python library: game database (T3DB), `.big` archives, textures, meshes, locale, crests, kits, photos, faces, 3D preview and the patch builder |
| `core/lzx/` | Source of `core/fsmod/bin/lzxdec.exe` (LZX decoder, libmspack) |
| `backend/fsapi/` | FastAPI server over `fsmod` (routes below) |
| `frontend/` | React + Vite + TypeScript + Tailwind + shadcn/ui (see `frontend/README.md`) |
| `desktop/` | Tauri packaging: installer and portable zip (see `desktop/README.md`) |

Not in git (each user has their own): `backend/original_files/` (the game's originals), `backend/patch/` (build
output), `backend/project/` (your mod: `database.json`, images, faces), `backend/config.json` and `backend/cache/`.

Tests:

```bat
cd core && python -m pytest -q
cd backend && python -m pytest -q
```

Tests that need the game's original files (or other local data) are skipped when they are not available. The
backend tests use temporary folders and a fake game; they never touch a real installation.

## API

| Route | What it does |
|---|---|
| `GET /api/status` | missing original files, config, `setup` (first-run state: `required`/`reasons`, the app's originals checked, ReStreet version, patch installed in the game and files changed outside the app — cheap, only changed files are hashed), project, patch state (`up_to_date` = built from the saved project) |
| `POST /api/setup/check` `{game_dir}` | checks a game folder: ReStreet root, version (`online-patch.json`), SHA-1 of the 12 files against the official ones (`fsapi/game_setup.py`), guess of the save folder |
| `POST /api/setup/apply` `{game_dir, save_dir, face_pack_dir, terms_version}` | saves the first-run choices; imports the 12 originals from the game (only official files) when the app does not have them verified |
| `POST /api/dialog/folder?initial=` | Windows folder picker on this machine; `{folder}` or null |
| `GET/PUT /api/config` | local settings |
| `GET/PUT /api/project`, `POST /api/project/validate` | project (contract v2) + validation issues (`code`, `severity`, `entity`, `field`, pt-BR `message`) + `defaults` (per player: values inherited from the template player where the project leaves a field unset) |
| `GET /api/project/backup` | zip of the project folder (`database.json` + `images/` + `faces/`), downloaded by the "Fazer backup" button |
| `POST /api/project/restore` (zip) | replaces the project with a backup zip (its content or the `project` folder itself); checked and extracted beside the folder first, so a bad zip (`invalid_backup` + `reason`) changes nothing |
| `POST /api/originals/teams/{teamid}/edit?uid=` | starts editing an original team: its crest and kits become provisional project images and the `Team` comes back filled with the game's data (`original_id`, `loaded` = what was loaded; the build only rewrites what changed) |
| `GET /api/originals/leagues`, `/teams`, `/players` | original game data, read-only (`players`: `team`, `q`, `offset`, `limit`); teams say `crest`, players say `photo` (has a menu image) |
| `GET /api/originals/crests/{teamid}.webp`, `/photos/{playerid}.webp` | menu crest / photo of an original team / player (128 px; 404 when the game has none), converted once and kept in `cache/originals/` |
| `GET /api/catalog` | valid values: free league ids, free team slots, positions, nations, appearance codes, skills, ranges |
| `POST /api/images` | upload an image into the project under a provisional name (`images/upload-…`); saving the project gives each image the fixed name of its entity (`images/teams/team-<uid>`, `images/players/player-<uid>`, `images/leagues/league-<uid>[-wide]`) and deletes the images and faces it no longer uses |
| `GET /api/images/{name}` | project image |
| `GET /api/preview/photo.png?path=` | player photo as the game shows it (256 px, DXT5) |
| `GET /api/preview/kit.png?jersey=r,g,b&crest=images/x.png` | kit-screen thumbnail for a jersey color + crest |
| `GET /api/preview/head/{headtypecode}.glb` | generic head mesh (nodes `head`, `eyes`; meters) |
| `GET /api/preview/hair/{hairtypecode}.glb` | hair mesh (nodes `cap`, `strands`); 404 for 0 = bald |
| `GET /api/preview/hair/{hairtypecode}/color.png` | grey hair texture (tinted by the viewer; first UV set) |
| `GET /api/preview/hair/{hairtypecode}/{cap\|strands}.png` | opacity of the cap (UV 0) or the strands (UV 1: atlas of locks) |
| `GET /api/preview/eyes/{eyecolorcode}.png` | eye texture |
| `GET /api/preview/body/{part}/{code}.glb` | one body part: jersey/arms (code = sleeve), socks/legs (sock length), shorts (0), shoes (shoe type), gloves (0); street pieces: top/bottom/streetsocks (code = style) |
| `GET /api/preview/street/{top\|bottom\|socks}/{style}/{pattern}.png` | street clothes texture: RGB = color mask (primary/secondary/tertiary), alpha = shading |
| `GET /api/preview/street/{top\|bottom\|socks}/{style}/{pattern}/crest.png?crest=` | crest decal over a street piece (same UV; transparent when the pattern carries no crest) |
| `GET /api/preview/skin/{tone}.png` / `shoe/{shoetypecode}.png` / `glove/{gkglovetypecode}.png` | skin of arms/legs / boot / goalkeeper glove texture |
| `GET /api/preview/kit/{jersey\|shorts}.png?color=r,g,b&crest=images/x.png` | team kit texture: solid color + crest decal + shading (shorts also cover the socks) |
| `GET /api/preview/face.png?headtypecode=&eyebrowcode=&sideburnscode=&facialhaircolorcode=&facialhairtypecode=&skintypecode=&skintonecode=` | face texture the game picks (skin, eyebrows, beard baked in) |
| `GET /api/facepack[?folder=]` | complete faces of the FIFA 14 face pack folder of the settings (`face_pack_dir`), or of `folder` (to check it before saving); read in place, never written. Each face says who the player is (`player`: name, club, nationality from the players base of the settings, `players_base_file`, by EA player id; `null` without a base or for an unknown id) |
| `POST /api/players-base/check` `{file}` | checks a players JSON against the contract (`fsapi/ea_players.py`): `{players, skipped, problems}`; 400 with `code` when the file cannot be used |
| `POST /api/players-base/browse` | Windows file picker for the players JSON; `{file}` or null |
| `POST /api/facepack/browse` | opens the Windows folder picker on this machine (tkinter, topmost); `{folder}` or null when cancelled |
| `GET /api/facepack/thumb.png?face=&folder=\|player=` | face seen from the front (gallery), from the pack or from the project |
| `POST /api/facepack/use` `{folder, face_id, player}` | copies that face's pack files into the project (`faces/<player uid>/`); the client then sets `player.face` |
| `GET /api/preview/scanned/{head.glb\|hair.glb\|hairlod.glb\|face.png\|eyes.png\|hair.png\|cap.png\|strands.png}?face=&haircolor=&folder=\|player=` | real face converted exactly like the build will (`fsmod.scanface`, ~3 s, cached) |
| `GET /api/preview/lodhead.glb` | head every player has at the normal play camera (`body/playerlod_head.rx3`) |
| `POST /api/patch/build` | validate + build `patch/` (assigns ids and saves them in the project) |
| `GET /api/patch/progress` | step of the current/last build (`builder.BUILD_STEPS`), done/total, last message, elapsed |
| `POST /api/patch/install` | copy `patch/Game` into the game's `Game` (game closed, free space checked; each file through a temporary name, everything put back if one fails; files that left the patch come back from `original_files`; manifest with size/mtime/SHA-1) and **delete the save** (no copy) |
| `POST /api/patch/uninstall` | originals back over what the patch changed, what it added removed (manifest), save deleted |
| `POST /api/patch/export` | zip of `patch/Game` saved where the user picks (Windows dialog); `{path}` or null |
| `POST /api/save/delete` | deletes the save (only a `…\4541097B` profile folder is ever touched) |

Both folders below mirror the root folder of a ReStreet 2.x install, so it is always clear where each
file comes from or goes to: `Game/` here = `Game/` in the game (ReStreet 1.x called it `GameData`).

## original_files/ (not in git — provide your own)

The app never touches the game installation. Copy these files from your game's `Game` folder (ReStreet
2.x) into `backend/original_files/Game/`, keeping the same relative paths:

```
original_files/
└─ Game/
   ├─ data0.big   data0.bh     (game database + its meta XML)
   ├─ data1.big   data1.bh     (menu crests, kit thumbnails; the 2.x one has the ReStreet menu credits)
   ├─ data3.big   data3.bh     (team kits, 3D meshes)
   ├─ data7.big   data7.bh     (street clothes textures, far hair of scanned faces)
   ├─ data/loc/locale.big      (game texts)
   ├─ data/loc/locale_ptbr.big (game texts in pt-BR, ReStreet 2.x)
   └─ data/ui/imgAssets/heads/2dheads.big   (player photos)
```

About 1.7 GB. They must be the untouched originals (never a modded copy): the patch contains whole copies
of the files it changes, so a modded or outdated original would end up in the game. Another location can
be used with the `FSMOD_ORIGINAL_FILES` environment variable (pointing to the folder that contains `Game`).

## patch/ (not in git — generated)

Output of a build, rebuilt from the originals every time (ReStreet 2.x has no `Mods` overlay, so the
changed game files go whole). Copy `Game/` over the game's `Game/` folder:

```
patch/
├─ Game/
│  ├─ data8.big   data8.bh     (database; the game reads d:\data8.big over data0)
│  ├─ data1.big   data1.bh     (menu crests, kit thumbnails)              ┐
│  ├─ data3.big   data3.bh     (team kits, heads)                         │ always all of them:
│  ├─ data7.big   data7.bh     (far hair of scanned faces)                │ modified when the project
│  ├─ data/loc/locale.big      (texts)                                    │ changes them, the plain
│  ├─ data/loc/locale_ptbr.big (texts, pt-BR)                             │ original otherwise
│  └─ data/ui/imgAssets/heads/2dheads.big/.bh   (player photos)           ┘
├─ .fsmod_build.json           (internal: lets the next build reuse the big files)
└─ patch.json                  (internal: project hash, file list)
```

Every file the app can change always goes (about 2 GB), so copying `Game/` over any earlier install
always leaves the game exactly as the project says: something removed from the project goes back to
the original even when the project no longer touches that file.

Keep a backup of the game's original files before copying (to remove the mod, copy them back; they are
the same as `original_files/`). After installing, the game needs a new save to see new teams/players. Override the output folder with
`FSMOD_PATCH_DIR`.
