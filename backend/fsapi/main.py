"""FastAPI app of the modding tool. Run: python -m fsapi (from backend) or start.bat."""
import datetime
import io
import os
import threading
import time

from fastapi import FastAPI, File, HTTPException, Path, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from . import settings  # noqa: F401  (puts core on sys.path)
from .messages import issue_json
from . import ea_players, game_setup
from .dialogs import browse_folder, open_file, save_file
from .faces import FaceError, FaceService
from .original_images import OriginalImages
from .patch_service import InstallError, build_patch, export_patch, install, installed_state, patch_status, uninstall
from .project_store import BackupError, ProjectStore, migrate_folder
from fsmod import builder, kit, model, photo, preview, scanface, validation
from fsmod.catalog import SKILLS, Catalog
from fsmod.game import GameSources, default_original_files, default_patch_dir

UID_PATTERN = r'^[A-Za-z0-9_-]+$'  # project uids (lg_/tm_/jg_...): used as folder names
NO_CACHE = {'Cache-Control': 'no-cache'}  # project images keep their name when replaced: always revalidate

INSTALL_ERROR_TEXT = {
    'game_dir_invalid': 'Configure a pasta do jogo (a que contém as pastas Game e Binaries).',
    'patch_missing': 'Gere o patch primeiro.',
    'game_running': 'Feche o jogo antes.',
    'save_dir_invalid': 'Configure a pasta do save (…\\fifastreet\\<perfil>\\4541097B).',
    'disk_full': 'Falta espaço no disco do jogo para instalar o patch.',
    'not_installed': 'Não há patch do app instalado nesse jogo.',
}


class AppState:
    """Process-wide state; the catalog is rebuilt only when the original files change."""

    def __init__(self, original_files=None, patch_dir=None, config_path=None):
        self.config_path = config_path
        self.config = settings.load_config(config_path)
        self.upgrade_project()
        self.patch_dir = patch_dir or default_patch_dir()
        self.load_game(original_files or default_original_files())
        self._lock = threading.Lock()
        self.build_lock = threading.Lock()
        self.build_progress = {'running': False}  # last/current build, read by GET /api/patch/progress

    def load_game(self, folder):
        """(Re)reads the originals folder: after importing originals nothing cached from the old files stays."""
        self.game = GameSources(folder)
        prints = os.path.join(os.path.dirname(os.path.abspath(self.config_path or settings.CONFIG_PATH)),
                              'originals_fingerprints.json')
        self.originals = game_setup.Originals(folder, prints)
        self.faces = FaceService(self.game)
        self.original_images = OriginalImages(self.game, os.path.join(os.path.dirname(prints), 'cache'))
        self._catalog = None

    def upgrade_project(self):
        """Projects of older versions of the app: the default folder moved from <repo>/projeto to the app data
        (settings.DEFAULT_PROJECT_DIR) and projeto.json became database.json."""
        if self.config.project_dir == settings.DEFAULT_PROJECT_DIR:
            moved = migrate_folder(settings.LEGACY_PROJECT_DIR, self.config.project_dir)
            if moved and os.path.exists(self.config_path or settings.CONFIG_PATH):
                settings.save_config(self.config, self.config_path)
        self.store.upgrade()

    @property
    def store(self):
        return ProjectStore(self.config.project_dir)

    def catalog(self):
        missing = self.game.missing_files()
        if missing:
            raise HTTPException(409, {'code': 'original_files_missing', 'missing': missing,
                                      'message': 'Faltam os arquivos originais do jogo: faça a configuração inicial.'})
        with self._lock:
            if self._catalog is None:
                self._catalog = Catalog(self.game)
            return self._catalog


def create_app(state=None):
    state = state or AppState()
    app = FastAPI(title='FS4 Patch Studio')
    app.state.fsmod = state

    def issues_for(project, raw=False):
        issues = validation.validate(project, state.catalog(), state.store.folder)
        return issues if raw else [issue_json(i) for i in issues]

    # ---------------------------------------------------------------- status / config
    def setup_state():
        """What the first-run screen needs: done when the originals are official, the game and save folders are set
        and the current notice was accepted. Cheap (only changed files are hashed again)."""
        cfg, originals = state.config, state.originals.state()
        reasons = [r for r, bad in (('originals', not originals['verified']),
                                    ('game_dir', not game_setup.is_game_root(cfg.game_dir)),
                                    ('save_dir', not game_setup.is_save_dir(cfg.save_dir)),
                                    ('terms', cfg.terms_version != game_setup.TERMS_VERSION)) if bad]
        version = game_setup.restreet_version(cfg.game_dir) if cfg.game_dir else None
        return {'required': bool(reasons), 'reasons': reasons, 'terms_version': game_setup.TERMS_VERSION,
                'originals': originals,
                'game': {'version': version, 'tested': version in game_setup.TESTED_VERSIONS,
                         'tested_versions': list(game_setup.TESTED_VERSIONS), **installed_state(cfg.game_dir)}}

    @app.get('/api/status')
    def status():
        store = state.store
        return {'original_files': {'folder': state.game.folder, 'missing': state.game.missing_files()},
                'config': state.config.model_dump(),
                'setup': setup_state(),
                'project': {'path': store.path, 'exists': store.exists()},
                'patch': {'folder': state.patch_dir, **patch_status(store, state.patch_dir)}}

    # ---------------------------------------------------------------- first-run setup
    class GameDir(BaseModel):
        game_dir: str

    @app.post('/api/setup/check')
    def setup_check(req: GameDir):
        """Checks a game folder the user picked (hashes the 12 files: a few seconds, longer on a hard disk) and
        guesses the save folder."""
        result = game_setup.check_game(req.game_dir)
        result['originals'] = state.originals.state()
        result['save_dir_guess'] = game_setup.guess_save_dir()
        return result

    class SetupRequest(BaseModel):
        game_dir: str
        save_dir: str
        face_pack_dir: str | None = None
        terms_version: int

    @app.post('/api/setup/apply')
    def setup_apply(req: SetupRequest):
        """Saves the first-run choices. The app's originals are imported from the game only when the app does not
        have them verified yet, and only if the game's files are the official ones."""
        def fail(code, message, **extra):
            raise HTTPException(409, {'code': code, 'message': message, **extra})
        if req.terms_version != game_setup.TERMS_VERSION:
            fail('terms_not_accepted', 'Aceite o aviso para continuar.')
        if not game_setup.is_game_root(req.game_dir):
            fail('game_dir_invalid', INSTALL_ERROR_TEXT['game_dir_invalid'])
        if not game_setup.is_save_dir(req.save_dir):
            fail('save_dir_invalid', 'Pasta do save não encontrada: abra o jogo uma vez (ele cria a pasta) e indique '
                                     'a pasta 4541097B dentro de Documentos\\fifastreet\\<perfil>.')
        if req.face_pack_dir:
            faces_call(state.faces.list, req.face_pack_dir)
        checked = game_setup.check_game(req.game_dir)
        if not checked['accepted']:  # another mod (or a patch copied by hand): the app could not undo it
            fail('game_files_not_official', 'Os arquivos do jogo não são os originais do ReStreet (o jogo já tem algum '
                 'mod ou um patch copiado à mão?). Use uma instalação limpa do ReStreet.',
                 files={k: v for k, v in checked['files'].items() if v != 'ok'})
        imported = []
        if not state.originals.state()['verified']:
            if not checked['official']:
                fail('game_files_not_official', 'O app ainda não tem os arquivos originais e este jogo está com o patch '
                     'do app: desinstale-o (ou use uma instalação limpa do ReStreet).')
            imported = state.originals.import_from(req.game_dir)
            state.load_game(state.game.folder)
        state.config = state.config.model_copy(update={
            'game_dir': req.game_dir, 'save_dir': req.save_dir, 'face_pack_dir': req.face_pack_dir or None,
            'terms_version': req.terms_version})
        settings.save_config(state.config, state.config_path)
        return {'imported': imported, 'setup': setup_state()}

    @app.post('/api/dialog/folder')
    def dialog_folder(initial: str | None = None):
        """Windows folder picker on the user's machine; {'folder': path or None (cancelled)}."""
        return {'folder': browse_folder(initial)}

    @app.get('/api/config')
    def get_config():
        return state.config.model_dump()

    @app.put('/api/config')
    def put_config(config: settings.Config):
        state.config = config
        settings.save_config(config, state.config_path)
        return config.model_dump()

    # ---------------------------------------------------------------- project
    @app.get('/api/project')
    def get_project():
        project = state.store.load()
        return {'project': project.to_json(), 'issues': issues_for(project),
                'defaults': state.catalog().player_defaults(project)}

    @app.put('/api/project')
    def put_project(project: model.Project):
        state.store.save(project)
        return {'project': project.to_json(), 'issues': issues_for(project),
                'defaults': state.catalog().player_defaults(project),
                'patch': patch_status(state.store, state.patch_dir)}

    BACKUP_ERROR_TEXT = {
        'not_a_zip': 'O arquivo não é um zip.',
        'no_database': 'O zip não tem o database.json do projeto.',
        'unsafe_path': 'O zip tem caminhos inválidos.',
        'too_big': 'O zip é grande demais para um backup do projeto.',
        'invalid_database': 'O database.json do zip não tem o formato de um projeto.',
    }

    @app.get('/api/project/backup')
    def project_backup():
        """Zip of the project folder (database.json + images + faces): the backup the user downloads."""
        buf = io.BytesIO()
        state.store.write_backup(buf)
        name = f'fifa-street-mod-backup-{datetime.date.today().isoformat()}.zip'
        return Response(buf.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="{name}"'})

    @app.post('/api/project/restore')
    def project_restore(file: UploadFile = File(...)):
        """Replaces the project with a backup zip (GET /api/project/backup)."""
        try:
            state.store.restore_backup(file.file)
        except BackupError as e:
            raise HTTPException(400, {'code': 'invalid_backup', 'reason': e.code, 'message': BACKUP_ERROR_TEXT[e.code]})
        return get_project()

    @app.post('/api/project/validate')
    def validate_project(project: model.Project):
        """Issues of a draft + the values each player inherits from its template player."""
        return {'issues': issues_for(project), 'defaults': state.catalog().player_defaults(project)}

    # ---------------------------------------------------------------- originals (read-only)
    @app.get('/api/originals/leagues')
    def original_leagues():
        return state.catalog().leagues

    @app.get('/api/originals/teams')
    def original_teams(league: int | None = None):
        teams = state.catalog().teams
        images = state.original_images
        return [{**t, 'crest': images.has_crest(t['id'])} for t in teams if league is None or t['league'] == league]

    @app.get('/api/originals/stadiums')
    def original_stadiums():
        return state.catalog().stadiums

    @app.get('/api/originals/players')
    def original_players(team: int | None = None, q: str | None = None,
                         offset: int = 0, limit: int = Query(100, le=5000)):
        players = state.catalog().players
        if team is not None:
            players = [p for p in players if team in p['teams']]
        if q:
            needle = q.lower()
            players = [p for p in players if needle in p['display_name'].lower()
                       or needle in f"{p['first_name']} {p['last_name']}".lower()]
        images = state.original_images
        return {'total': len(players),
                'items': [{**p, 'photo': images.has_photo(p['id'])} for p in players[offset:offset + limit]]}

    ORIGINAL_IMAGE_CACHE = {'Cache-Control': 'public, max-age=86400'}

    @app.get('/api/originals/crests/{teamid}.webp')
    def original_crest(teamid: int):
        """Menu crest of an original team (128 px); 404 for the game's internal teams, which have none."""
        state.catalog()  # 409 when original files are missing
        data = state.original_images.crest(teamid)
        if data is None:
            raise HTTPException(404)
        return Response(data, media_type='image/webp', headers=ORIGINAL_IMAGE_CACHE)

    @app.get('/api/originals/photos/{playerid}.webp')
    def original_photo(playerid: int):
        """Menu photo of an original player (128 px); 404 when the game has none (most generic heads)."""
        state.catalog()
        data = state.original_images.photo(playerid)
        if data is None:
            raise HTTPException(404)
        return Response(data, media_type='image/webp', headers=ORIGINAL_IMAGE_CACHE)

    # ---------------------------------------------------------------- valid values
    @app.get('/api/catalog')
    def catalog():
        c = state.catalog()
        return {'positions': c.positions,
                'nations': c.nations, 'appearance': c.appearance_options,
                'skills': {k: {'min': lo, 'max': hi} for k, (lo, hi) in SKILLS.items()},
                'template_teams': [t for t in c.teams if t['generic']],
                'max_roster': builder.MAX_ROSTER,
                'max_leagues': len(builder.IMAGE_COUNTRIES), 'max_league_teams': builder.MAX_LEAGUE_TEAMS,
                'hair_colors': {code: preview.hair_color(code) for code in c.appearance_options['haircolorcode']},
                'lineup_modes': c.lineup_modes,
                'street_options': c.street_options,
                'street_arms': preview.STREET_ARMS,
                'street_full_length_bottoms': preview.STREET_FULL_LENGTH_BOTTOMS,
                'template_street': {t['id']: c.template_street(t['id']) for t in c.teams if t['generic']},
                'ranges': {'height': c.field_range('players', 'height'), 'weight': c.field_range('players', 'weight'),
                           'number': c.field_range('teamplayerlinks', 'jerseynumber')}}

    # ---------------------------------------------------------------- images
    @app.post('/api/images')
    async def upload_image(file: UploadFile = File(...)):
        """Stores an image in the project under a provisional name; saving the project gives it the fixed name of
        its entity (teams/team-<uid>, teams/kits/team-<uid>-<slot>-<part>, players/player-<uid>,
        leagues/league-<uid>[-wide]). Any image fits (bigger game entries move to the
        end of the archive)."""
        data = await file.read()
        try:
            Image.open(io.BytesIO(data)).verify()
            path = state.store.save_image(file.filename, data)
        except Exception:
            raise HTTPException(400, {'code': 'invalid_image', 'message': 'Arquivo de imagem inválido.'})
        return {'path': path}

    def project_image(path):
        try:
            full = state.store.image_path(path)
        except ValueError:
            raise HTTPException(400, 'invalid image path')
        if not os.path.isfile(full):
            raise HTTPException(404)
        return full

    @app.get('/api/preview/photo.png')
    def photo_preview(path: str):
        """Player photo as the game shows it (square crop, photo.SIZE px, DXT5)."""
        im = photo.preview(Image.open(project_image(path)))
        buf = io.BytesIO()
        im.save(buf, format='PNG')
        return Response(buf.getvalue(), media_type='image/png', headers=NO_CACHE)

    @app.get('/api/images/{name:path}')
    def get_image(name: str):
        try:
            path = state.store.image_path(f'images/{name}')
        except ValueError:
            raise HTTPException(400, 'invalid image path')
        if not os.path.isfile(path):
            raise HTTPException(404)
        return FileResponse(path, headers=NO_CACHE)

    @app.get('/api/preview/kit.png')
    def kit_preview(jersey: str = Query(..., pattern=r'^\d{1,3},\d{1,3},\d{1,3}$'), crest: str | None = None):
        """Kit-screen thumbnail for a jersey color (r,g,b) and an optional project crest image."""
        rgb = tuple(int(v) for v in jersey.split(','))
        if any(v > 255 for v in rgb):
            raise HTTPException(400, 'invalid color')
        crest_img = Image.new('RGBA', (26, 26), (0, 0, 0, 0))
        if crest:
            try:
                path = state.store.image_path(crest)
            except ValueError:
                raise HTTPException(400, 'invalid image path')
            if os.path.isfile(path):
                crest_img = Image.open(path).convert('RGBA')
        state.catalog()
        im, _ = kit.thumbnail(state.game, rgb, crest_img)
        buf = io.BytesIO()
        im.save(buf, format='PNG')
        return Response(buf.getvalue(), media_type='image/png')

    # ---------------------------------------------------------------- real faces (FIFA 14 packs)
    class FacePick(BaseModel):
        folder: str
        face_id: int
        player: str

    def faces_call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FaceError as e:
            raise HTTPException(e.status, {'code': e.code, 'message': e.message})

    def png_response(data, cache=True):
        return Response(data, media_type='image/png', headers=PREVIEW_CACHE if cache else None)

    @app.post('/api/facepack/browse')
    def facepack_browse():
        """Opens the Windows folder picker on the user's machine; {'folder': path or None (cancelled)}."""
        return {'folder': browse_folder(state.config.face_pack_dir, 'Pasta do pack de faces (FIFA 14)')}

    @app.get('/api/facepack')
    def facepack_list(folder: str | None = None):
        """Complete faces of a pack folder: the one in the settings (face_pack_dir), or `folder` (to check a folder
        before saving it in the settings). Each face says who the player is (`player`: name, club, nationality from
        the players base of the settings, fsapi.ea_players) when there is a base and it knows the id."""
        folder = folder or state.config.face_pack_dir
        if not folder:
            raise HTTPException(404, {'code': 'facepack_not_set',
                                      'message': 'Indique a pasta do pack de faces nas Configurações.'})
        pack = faces_call(state.faces.list, folder)
        base = state.config.players_base_file
        return {**pack, 'faces': [{**f, 'player': ea_players.summary(base, f['id'])} for f in pack['faces']]}

    # ---------------------------------------------------------------- players base (who each EA player id is)
    class PlayersBaseFile(BaseModel):
        file: str

    @app.post('/api/players-base/check')
    def players_base_check(req: PlayersBaseFile):
        """Checks a players JSON against the contract (fsapi.ea_players) before it is kept in the settings: usable
        players, skipped records and the first problems; 400 when the file cannot be used at all."""
        try:
            return ea_players.check(req.file)
        except ea_players.PlayersBaseError as e:
            raise HTTPException(400, {'code': e.code, 'message': e.message})

    def players_base_file():
        file = state.config.players_base_file
        if not file:
            raise HTTPException(404, {'code': 'players_base_not_set',
                                      'message': 'Indique a base de jogadores nas Configurações.'})
        return file

    @app.get('/api/players-base/players')
    def players_base_search(q: str = '', limit: int = Query(50, le=500)):
        """Players of the base of the settings matching q (id, name or club; accents ignored)."""
        try:
            return ea_players.search(players_base_file(), q, limit)
        except ea_players.PlayersBaseError as e:
            raise HTTPException(400, {'code': e.code, 'message': e.message})

    @app.get('/api/players-base/players/{player_id}')
    def players_base_player(player_id: int):
        """The contract fields the base has for one player (names, birth date, height, weight, foot, skill bars
        converted from the FIFA attributes...) + `nation_id`, the game nation of its nationality when one matches."""
        try:
            rec = ea_players.record(players_base_file(), player_id)
        except ea_players.PlayersBaseError as e:
            raise HTTPException(400, {'code': e.code, 'message': e.message})
        if not rec:
            raise HTTPException(404, {'code': 'players_base_unknown_id', 'message': 'Jogador fora da base.'})
        nation = ea_players.nation_id(rec.get('nationality'), state.catalog().nation_names)
        return {**rec, 'nation_id': nation} if nation is not None else rec

    @app.post('/api/players-base/browse')
    def players_base_browse():
        return {'file': open_file(state.config.players_base_file, 'Base de jogadores (JSON)')}

    @app.get('/api/facepack/thumb.png')
    def facepack_thumb(face: int, folder: str | None = None, player: str | None = None):
        """Face seen from the front (gallery), from a pack (folder) or from the project (player uid)."""
        if not (folder or player):
            raise HTTPException(404)
        key, files = faces_call(state.faces.source_files, folder, face, state.store.folder, player)
        return png_response(state.faces.thumbnail(key, files))

    @app.post('/api/facepack/use')
    def facepack_use(pick: FacePick):
        """Copies the face's files into the project (faces/<player uid>/); the client then sets player.face."""
        pack = faces_call(state.faces.copy_to_project, pick.folder, pick.face_id, state.store.folder, pick.player)
        return {'face': {'source_id': pick.face_id, 'pack': pack}}

    class FaceCopy(BaseModel):
        from_player: str = Field(pattern=UID_PATTERN)
        to_player: str = Field(pattern=UID_PATTERN)
        face_id: int

    @app.post('/api/faces/copy')
    def faces_copy(copy: FaceCopy):
        """Copies a player's real face files to another player of the project (the "Copy" of a player)."""
        folder = state.store.folder
        files = scanface.read_files(scanface.project_face_dir(folder, copy.from_player), copy.face_id)
        if not files:
            raise HTTPException(404, {'code': 'face_not_found', 'message': 'Face do jogador original não encontrada.'})
        scanface.write_files(scanface.project_face_dir(folder, copy.to_player), copy.face_id, files)
        return {'ok': True}

    SCANNED_ASSETS = {'head.glb', 'hair.glb', 'hairlod.glb', 'face.png', 'eyes.png', 'hair.png', 'cap.png', 'strands.png'}

    @app.get('/api/preview/scanned/{asset}')
    def scanned_preview(asset: str, face: int, haircolor: int = 0, paint: bool = True, folder: str | None = None,
                        player: str | None = None, hair: str = 'standard',
                        thick: float = Query(scanface.HAIR_THICKNESS, ge=0, le=scanface.HAIR_THICKNESS_MAX)):
        """Converted real face (what the build writes), from a pack (folder) or from the project (player uid);
        hair = hair converter (scanface.HAIR_MODES), thick = its strand thickness."""
        if asset not in SCANNED_ASSETS or not (folder or player) or hair not in scanface.HAIR_MODES:
            raise HTTPException(404)
        state.catalog()  # 409 when original files are missing (the template lives there)
        key, files = faces_call(state.faces.source_files, folder, face, state.store.folder, player)
        try:
            c = state.faces.converted(key, files, haircolor, paint, hair, thick)
        except ValueError as e:
            raise HTTPException(422, {'code': 'face_conversion_failed', 'message': f'Não deu para converter esta face: {e}'})
        hair_parts = {'hair.glb': 'hair', 'hairlod.glb': 'hairlod'}
        if asset == 'head.glb':
            return Response(preview.head_glb_of(c['head']), media_type='model/gltf-binary', headers=PREVIEW_CACHE)
        if asset in hair_parts:  # no hair in the pack: empty model (the viewer then draws nothing)
            glb = preview.hair_glb_of(c[hair_parts[asset]]) if hair_parts[asset] in c else preview.gltf.write_glb([])
            return Response(glb, media_type='model/gltf-binary', headers=PREVIEW_CACHE)
        if asset in ('face.png', 'eyes.png'):
            return png_response(preview.texture_png(c[asset[:-4]]))
        if 'hair_textures' not in c:
            buf = io.BytesIO()
            Image.new('L', (1, 1), 0).save(buf, format='PNG')
            return png_response(buf.getvalue())
        if asset == 'hair.png':
            return png_response(preview.hair_color_png_of(c['hair_textures']))
        return png_response(preview.hair_alpha_png_of(c['hair_textures'], asset[:-4]))

    @app.get('/api/preview/lodhead.glb')
    def lod_head_preview():
        """Head every player has at the normal play camera (drawn with the player's face texture)."""
        return Response(preview_asset(preview.lod_head_glb), media_type='model/gltf-binary', headers=PREVIEW_CACHE)

    # ---------------------------------------------------------------- 3D preview (generic heads)
    PREVIEW_CACHE = {'Cache-Control': 'public, max-age=86400'}

    def preview_asset(fn, *args):
        state.catalog()  # 409 when original files are missing
        try:
            return fn(state.game, *args)
        except KeyError:
            raise HTTPException(404, {'code': 'preview_asset_missing', 'message': 'Arquivo do jogo não encontrado.'})

    @app.get('/api/preview/head/{headtypecode}.glb')
    def head_preview(headtypecode: int):
        """Generic head mesh (nodes 'head' and 'eyes'), meters."""
        return Response(preview_asset(preview.head_glb, headtypecode), media_type='model/gltf-binary',
                        headers=PREVIEW_CACHE)

    @app.get('/api/preview/hair/{hairtypecode}.glb')
    def hair_preview(hairtypecode: int):
        """Hair mesh (nodes 'cap' and/or 'strands'); 404 for hairtypecode 0 (bald)."""
        glb = preview_asset(preview.hair_glb, hairtypecode)
        if glb is None:
            raise HTTPException(404, {'code': 'preview_asset_missing', 'message': 'Sem cabelo.'})
        return Response(glb, media_type='model/gltf-binary', headers=PREVIEW_CACHE)

    @app.get('/api/preview/hair/{hairtypecode}/color.png')
    def hair_color_preview(hairtypecode: int):
        """Grey hair texture, tinted by the viewer (first UV set)."""
        return Response(preview_asset(preview.hair_color_png, hairtypecode), media_type='image/png',
                        headers=PREVIEW_CACHE)

    @app.get('/api/preview/hair/{hairtypecode}/{part}.png')
    def hair_alpha_preview(hairtypecode: int, part: str = Path(..., pattern='^(cap|strands)$')):
        """Opacity of the cap (first UV set) or the strands (second UV set, an atlas of locks)."""
        return Response(preview_asset(preview.hair_alpha_png, hairtypecode, part), media_type='image/png',
                        headers=PREVIEW_CACHE)

    @app.get('/api/preview/eyes/{eyecolorcode}.png')
    def eyes_preview(eyecolorcode: int):
        return Response(preview_asset(preview.eyes_png, eyecolorcode), media_type='image/png', headers=PREVIEW_CACHE)

    @app.get('/api/preview/face.png')
    def face_preview(headtypecode: int = 0, eyebrowcode: int = 0, sideburnscode: int = 0, facialhaircolorcode: int = 0,
                     facialhairtypecode: int = 0, skintypecode: int = 0, skintonecode: int = 2):
        """Face texture (skin, eyebrows and beard baked in) the game picks for these codes."""
        appearance = {'headtypecode': headtypecode, 'eyebrowcode': eyebrowcode, 'sideburnscode': sideburnscode,
                      'facialhaircolorcode': facialhaircolorcode, 'facialhairtypecode': facialhairtypecode,
                      'skintypecode': skintypecode, 'skintonecode': skintonecode}
        return Response(preview_asset(preview.face_png, appearance), media_type='image/png', headers=PREVIEW_CACHE)

    @app.get('/api/preview/body/{part}/{code}.glb')
    def body_preview(code: int, part: str = Path(..., pattern='^(jersey|shorts|socks|arms|legs|shoes|gloves|top|bottom|streetsocks)$'),
                     collar: int = Query(0, ge=0, le=14)):
        """One body part of the team kit body; code = sleeve (jersey, arms), sock length (socks, legs) or shoe type;
        collar = jersey collar mesh (real kits)."""
        return Response(preview_asset(preview.body_part_glb, part, code, collar), media_type='model/gltf-binary',
                        headers=PREVIEW_CACHE)

    @app.get('/api/preview/glove/{code}.png')
    def glove_preview(code: int):
        """Goalkeeper glove texture (gkglovetypecode; 0, which has no file, shows type 1)."""
        return Response(preview_asset(preview.glove_png, code), media_type='image/png', headers=PREVIEW_CACHE)

    @app.get('/api/preview/street/{part}/{style}/{pattern}.png')
    def street_preview(style: int, pattern: int, part: str = Path(..., pattern='^(top|bottom|socks)$')):
        """Street clothes texture: RGB = color mask (primary/secondary/tertiary), alpha = shading."""
        return Response(preview_asset(preview.street_png, part, style, pattern), media_type='image/png',
                        headers=PREVIEW_CACHE)

    @app.get('/api/preview/street/{part}/{style}/{pattern}/crest.png')
    def street_crest_preview(style: int, pattern: int, part: str = Path(..., pattern='^(top|bottom|socks)$'),
                             crest: str | None = None):
        """Crest decal over a street piece (same UV as its texture; transparent when the pattern has no crest)."""
        crest_img = Image.open(project_image(crest)) if crest else None
        return Response(preview_asset(preview.street_crest_png, part, style, pattern, crest_img),
                        media_type='image/png')

    @app.get('/api/preview/skin/{tone}.png')
    def skin_preview(tone: int):
        return Response(preview_asset(preview.skin_png, tone), media_type='image/png', headers=PREVIEW_CACHE)

    @app.get('/api/preview/shoe/{shoe}.png')
    def shoe_preview(shoe: int):
        return Response(preview_asset(preview.shoe_png, shoe), media_type='image/png', headers=PREVIEW_CACHE)

    @app.get('/api/preview/kit/{part}.png')
    def kit_texture_preview(part: str = Path(..., pattern='^(jersey|shorts)$'),
                            color: str = Query(..., pattern=r'^\d{1,3},\d{1,3},\d{1,3}$'), crest: str | None = None):
        """Team kit texture (solid color + crest decal, shaded) as the game draws it; shorts also cover the socks."""
        rgb = tuple(int(v) for v in color.split(','))
        if any(v > 255 for v in rgb):
            raise HTTPException(400, 'invalid color')
        crest_img = Image.open(project_image(crest)) if crest else None
        return Response(preview_asset(preview.kit_png, part, rgb, crest_img), media_type='image/png')

    @app.get('/api/preview/real-kit/{part}.png')
    def real_kit_texture_preview(image: str, part: str = Path(..., pattern='^(jersey|shorts)$')):
        """Real kit texture (project PNG of a FIFA 14-16 kit) as the game draws it; shorts also cover the socks."""
        return Response(preview_asset(preview.real_kit_png, part, Image.open(project_image(image))),
                        media_type='image/png')

    # ---------------------------------------------------------------- patch
    @app.post('/api/patch/build')
    def build():
        project = state.store.load()
        issues = issues_for(project, raw=True)
        if validation.has_errors(issues):
            raise HTTPException(422, {'code': 'project_has_errors', 'issues': [issue_json(i) for i in issues],
                                      'message': 'Corrija os erros do projeto antes de gerar o patch.'})
        with state.build_lock:
            prog = state.build_progress = {'running': True, 'steps': list(builder.BUILD_STEPS), 'step': None,
                                           'done': 0, 'total': 0, 'message': '', 'started_at': time.time(),
                                           'finished_at': None, 'error': None}

            def progress(step, done, total):
                prog.update(step=step, done=done, total=total)

            def log(line):
                if not line.startswith(' '):  # leagues / teams / summary, not every player and file
                    prog['message'] = line

            try:
                result = build_patch(project, state.store, state.game, state.patch_dir, log=log, progress=progress)
            except builder.BuildError as e:
                prog['error'] = str(e)
                raise HTTPException(422, {'code': 'build_failed', 'entity': e.entity, 'message': str(e)})
            except Exception as e:
                prog['error'] = str(e)
                raise
            finally:
                prog.update(running=False, finished_at=time.time())
        return {'log': result.log, 'assigned_league_ids': result.assigned_league_ids,
                'assigned_team_ids': result.assigned_team_ids,
                'assigned_player_ids': result.assigned_player_ids,
                'patch': patch_status(state.store, state.patch_dir)}

    @app.get('/api/patch/progress')
    def build_progress():
        """Where the current (or last) build is: step (builder.BUILD_STEPS), done/total of that step, last message."""
        prog = dict(state.build_progress)
        if prog.get('started_at'):
            prog['elapsed'] = round((prog['finished_at'] or time.time()) - prog['started_at'], 1)
        return prog

    def game_action(fn, *args):
        if not state.originals.state()['verified']:
            raise HTTPException(409, {'code': 'originals_not_verified',
                                      'message': 'Os arquivos originais do app mudaram: refaça a configuração inicial.'})
        try:
            return fn(*args)
        except (InstallError, game_setup.SetupError) as e:
            raise HTTPException(409, {'code': str(e), 'message': INSTALL_ERROR_TEXT.get(str(e), str(e))})

    @app.post('/api/patch/install')
    def install_patch():
        """Copies the patch into the game and deletes the save (the game makes a new one)."""
        cfg = state.config
        if not patch_status(state.store, state.patch_dir)['up_to_date']:
            raise HTTPException(409, {'code': 'patch_outdated', 'message': 'O patch está desatualizado; gere de novo antes de instalar.'})
        return game_action(install, state.patch_dir, cfg.game_dir, cfg.backups_dir, state.game.folder, cfg.save_dir)

    @app.post('/api/patch/uninstall')
    def uninstall_patch():
        """Puts the game's original files back, removes what the patch added and deletes the save."""
        cfg = state.config
        return game_action(uninstall, cfg.game_dir, state.game.folder, cfg.save_dir)

    @app.post('/api/patch/export')
    def export():
        """Zip of the patch's Game folder, saved where the user picks (Windows dialog); {'path': None} if cancelled."""
        if not patch_status(state.store, state.patch_dir)['up_to_date']:
            raise HTTPException(409, {'code': 'patch_outdated', 'message': 'O patch está desatualizado; gere de novo antes de exportar.'})
        path = save_file('patch-fifa-street.zip', title='Exportar patch')
        if not path:
            return {'path': None}
        try:
            return export_patch(state.patch_dir, path)
        except InstallError as e:
            raise HTTPException(409, {'code': str(e), 'message': INSTALL_ERROR_TEXT.get(str(e), str(e))})

    @app.post('/api/save/delete')
    def delete_save():
        """Deletes the game's save (no copy); the game creates a new one from the database."""
        try:
            return {'removed': game_setup.delete_save(state.config.save_dir)}
        except game_setup.SetupError as e:
            raise HTTPException(409, {'code': str(e), 'message': INSTALL_ERROR_TEXT.get(str(e), str(e))})

    # ---------------------------------------------------------------- frontend (built files)
    # single-page app: real files are served as-is, any other non-API path gets index.html
    if os.path.isdir(settings.FRONTEND_DIST):
        assets = os.path.join(settings.FRONTEND_DIST, 'assets')
        if os.path.isdir(assets):
            app.mount('/assets', StaticFiles(directory=assets), name='assets')

        @app.get('/{path:path}', include_in_schema=False)
        def frontend(path: str):
            if path.startswith('api/'):
                raise HTTPException(404)
            full = os.path.abspath(os.path.join(settings.FRONTEND_DIST, path))
            if path and full.startswith(os.path.abspath(settings.FRONTEND_DIST)) and os.path.isfile(full):
                return FileResponse(full)
            # never cached: after an update the browser must load the new bundle (assets have hashed names)
            return FileResponse(os.path.join(settings.FRONTEND_DIST, 'index.html'), headers={'Cache-Control': 'no-cache'})

    return app


app = create_app() if os.environ.get('FSMOD_NO_DEFAULT_APP') != '1' else None
