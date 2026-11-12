// Mirrors core/fsmod/model.py (contract v2) and the backend responses.

export type RGB = [number, number, number]
export type KitKind = 'home' | 'away'
export type KitPart = 'jersey' | 'shorts' | 'socks'
export type RealKitSlot = 'home' | 'away' | 'goalkeeper'
export type TakerRole = 'penalty' | 'free_kick' | 'long_free_kick' | 'left_corner' | 'right_corner'
export type PlayerRef = string | number // project player uid, or playerid of one of the game's own players
export type TeamKey = string | number // new team uid, or teamid of one of the game's teams (edited or not)
export type RealKitFile = 'thumbnail' | 'jersey' | 'shorts'

/** Real kit of a FIFA 14-16 pack for one slot (fsmod.model.RealKit); a slot without jersey or shorts is not used. */
export interface RealKit {
  thumbnail?: string // kit-screen thumbnail; none = generic one tinted with the jersey
  jersey?: string // 2048x2048
  shorts?: string // 2048x1024
  name_color: RGB
  number_color: number // palette index (NUMBER_COLORS)
  shorts_number_color: number
  collar: number // 0-14
  front_number: boolean
  shorts_number?: boolean // number on the shorts; unset = the row's (new team: off; original: the game's)
}

/** When an entry of the project was created and last changed (ISO 8601, UTC), set by the backend on save; entries
 * saved before contract 9 have none until they change. */
export interface Dated {
  created_at?: string | null
  updated_at?: string | null
}

export interface League extends Dated {
  uid: string
  league_id?: number | null // leagueid in the game, given by the build
  name: string
  short_name?: string
  internal_name?: string
  sort_order: number
  image?: string
  wide_image?: string
  wide_image_fit?: 'contain' | 'cover'
  hidden?: boolean // left out of the patch (with its teams)
  original_id?: number | null // the game's own league this entry edits (same leagueid); none = new
  loaded?: unknown // original league: what was loaded from the game (compared by the backend)
}

/** What a team names its league by: a new league's uid or an original league's id. */
export type LeagueKey = number | string

export interface Team extends Dated {
  uid: string
  name: string
  leagues: LeagueKey[] // new league uids / original league ids it plays in; none = left out of the patch
  primary_color: RGB
  secondary_color: RGB
  team_id?: number | null // teamid in the game, given by the build
  original_id?: number | null // the game's own team this entry edits (same teamid); null = new team
  loaded?: { team: Record<string, unknown>; images: Record<string, string> } // what was loaded from the game
  short_name?: string
  name_10?: string
  name_7?: string
  abbreviation?: string
  crest?: string
  kits: Partial<Record<KitKind, Partial<Record<KitPart, RGB>>>>
  street_kits?: Partial<Record<KitKind, StreetKit>>
  use_real_kits?: boolean // team kits from real_kits instead of solid color + crest
  real_kits?: Partial<Record<RealKitSlot, RealKit>>
  kit_credits?: string // who made the real kits: one credit for the three
  kit_credits_url?: string // their page (http/https only)
  template: number
  captain?: PlayerRef // project player uid or the game's playerid; none = new team: first player, original: the game's
  takers?: Partial<Record<TakerRole, PlayerRef>> // set pieces; a role left out = the captain (original: the game's)
  lineups?: Lineup[] // starting lineup per game mode; a mode without one = the game's pick
  hidden?: boolean // left out of the patch (with its players)
}

/** Starting lineup of one game mode (fs4lineup); it seeds a new save. */
export interface Lineup {
  players: number // 1-6
  goalkeeper: boolean
  tactic: number // 0 static, 1 dynamic, 2 street (only 5 and 6 players have 0 and 2)
  starters: (PlayerRef | null)[] // player per slot; null = filled by the build
  reserves: PlayerRef[] // bench order; players left out follow in roster order
  // players: project player uids and/or playerids of the game's players
}

/** One team of a player (a teamplayerlinks row), with its own number and position. */
export interface TeamLink {
  team: TeamKey
  number?: number | null // unset: new team = the template's (game player: his own); game team = a free one
  position?: number | null // unset: new team = the template's (game player: his own); game team = his first team's
}

/** A game mode a lineup can be set for: {tactic id: area per starter slot} (0 GK, 1 DEF, 2 ATT). */
export interface LineupMode {
  players: number
  goalkeeper: boolean
  tactics: Record<string, number[]>
}

export type StreetPartName = 'top' | 'bottom' | 'socks'

/** One street kit piece: mesh type, texture variation and the colors painted on its mask (primary/secondary/tertiary). */
export interface StreetPiece {
  style: number
  pattern: number
  colors: [RGB, RGB, RGB]
}

/** A piece the game can pick: mesh type and texture variation (socks: style -1 = no socks). */
export interface StreetSlot {
  style: number
  pattern: number
}

/** One part of a street kit: the pieces the game picks from (per player, per match) and their 3 colors. */
export interface StreetPart {
  pieces: StreetSlot[]
  colors: [RGB, RGB, RGB]
}

/** Street Home/Away; a missing part keeps the template's pieces. */
export type StreetKit = Partial<Record<StreetPartName, StreetPart>>

export interface Player extends Dated {
  uid: string
  first_name: string
  last_name: string
  player_id?: number | null // playerid in the game, given by the build
  original_id?: number | null // the game's own player this entry edits (same playerid); null = new player
  loaded?: { player: Record<string, unknown>; images: Record<string, string> } // what was loaded from the game
  teams: TeamLink[] // clubs and national teams; none = free agent (kept only in the app)
  generic: boolean // false + no face: an original player keeps the game's scanned head
  display_name?: string
  jersey_name?: string
  template?: number
  height?: number
  weight?: number
  birthdate?: string
  foot?: 'right' | 'left'
  skills: Record<string, number>
  appearance: Record<string, number>
  fields: Record<string, number>
  photo?: string
  face?: ScannedFace // used when generic is false
  /** boot per pitch surface: uid of a new Boot of the project; a surface left out = the appearance code */
  boots?: Partial<Record<ShoeSurface, string>>
  /** goalkeeper glove picked in the Accessories tab: a new Glove's uid or a game glove's code; none = not picked
   * (gkglovetypecode stays as it is). A picked glove makes him a goalkeeper (lib/gloves preferredPosition). */
  glove?: string | number | null
  hidden?: boolean // left out of the patch (its id stays reserved)
}

/** Pitch surfaces with a boot of their own: street = shoetypecode, turf (society) = turf_shoe, indoor (futsal) =
 * indoor_shoe. The street only takes some codes (Boot.street / OriginalBoot.street). */
export type ShoeSurface = 'street' | 'turf' | 'indoor'
export const SHOE_SURFACES: ShoeSurface[] = ['street', 'turf', 'indoor']
export const SURFACE_FIELDS: Record<ShoeSurface, string> = { street: 'shoetypecode', turf: 'turf_shoe', indoor: 'indoor_shoe' }

/** A boot of the project: a new one (pack files, its code given by the build) or one of the game's boots the user
 * edits (original_id = its code; new files replace the game's for every player wearing it). Files are project
 * paths, kept as the user sent them. */
export interface Boot extends Dated {
  uid: string
  name: string
  credits?: string
  credits_url?: string // their page (http/https only)
  street?: boolean // may go on the street (takes one of the few free street codes; new boots only)
  code?: number | null // new boot: its code in the game, given by the build
  mesh?: string // the pack's shoe_<id>.rx3
  texture?: string // the pack's shoe_<id>_0_textures.rx3
  thumbnail?: string // picture in the app (image path); none = drawn from the files
  hidden?: boolean // left out of the patch
  original_id?: number | null // the game's boot this entry edits (its code)
}

/** One of the game's boots. */
export interface OriginalBoot {
  code: number
  street: boolean // may go on the street (codes 500-619)
  players: number // how many of the game's players wear it, on any surface
}

/** Boots of a shared zip (manifest.json), each with a new uid and its files as provisional uploads. */
/** A goalkeeper glove of the project: a new one (a FIFA 16 pack file, its code given by the build) or one of the
 * game's gloves the user edits (original_id = its code; a new file replaces the game's for every goalkeeper wearing
 * it). The file is a project path, kept as the user sent it. */
export interface Glove extends Dated {
  uid: string
  name: string
  credits?: string
  credits_url?: string // their page (http/https only)
  code?: number | null // new glove: its code in the game, given by the build
  texture?: string // the pack's gkglove_<id>_textures.rx3
  thumbnail?: string // picture in the app (image path); none = drawn from the file
  hidden?: boolean // left out of the patch
  original_id?: number | null // the game's glove this entry edits (its code)
}

/** One of the game's gloves. */
export interface OriginalGlove {
  code: number
  players: number // how many of the game's players have its code (only goalkeepers wear it in a match)
}

/** Gloves of a shared zip (manifest.json), each with a new uid and its files as provisional uploads. */
export interface GloveImport {
  kind: 'one' | 'many'
  gloves: Glove[]
  problems: { index: number; name: string; field: 'texture' | 'thumbnail'; code: string; message: string }[]
}

/** A ball of the project: a new one (FIFA 16 pack files, its id given by the build) or one of the game's balls the
 * user edits (original_id = its id; new files replace the game's for every stadium using it). Files are project
 * paths, kept as the user sent them. Stadiums pick it in originals.stadium_balls. */
export interface Ball extends Dated {
  uid: string
  name: string
  credits?: string
  credits_url?: string // their page (http/https only)
  code?: number | null // new ball: its id in the game, given by the build
  mesh?: string // the pack's ball_<id>.rx3
  texture?: string // the pack's ball_<id>_textures.rx3
  thumbnail?: string // picture in the app (image path); none = drawn from the files
  hidden?: boolean // left out of the patch
  original_id?: number | null // the game's ball this entry edits (its id)
}

/** One of the game's balls. */
export interface OriginalBall {
  id: number
  name: string | null // the game's name for it (most street balls have none)
  stadiums: number // how many stadium rows (stadiums and country versions) use it in the game
}

/** Balls of a shared zip (manifest.json), each with a new uid and its files as provisional uploads. */
export interface BallImport {
  kind: 'one' | 'many'
  balls: Ball[]
  problems: { index: number; name: string; field: 'mesh' | 'texture' | 'thumbnail'; code: string; message: string }[]
}

/** Leagues, teams and players shared in a zip (backend share_service): what a zip holds, before anything changes. */
export type ShareKind = 'leagues' | 'teams' | 'players'
export interface ShareProblem {
  index: number
  name: string
  field: string | null
  code: string
  message: string
}
export interface ShareInspect<T> {
  token: string // names the staged zip for apply
  items: T[] // entries as in the zip (file fields name files of the zip; problem files already left empty)
  problems: ShareProblem[]
}

export interface BootImport {
  kind: 'one' | 'many'
  boots: Boot[]
  problems: { index: number; name: string; field: 'mesh' | 'texture' | 'thumbnail'; code: string; message: string }[]
}

/** Real face from a FIFA 14 pack; its files are copied into the project (faces/<player uid>/). */
export interface ScannedFace {
  source_id: number
  pack?: string
  paint_scalp?: boolean // hair color painted on the scalp by the converter (missing = true, as older versions saved it; new faces come with false)
  hair_mode?: HairMode // hair converter (missing = 'standard'; new faces: NEW_FACE_HAIR_MODE)
  hair_thickness?: number // strand thickness of the 'split_sharp_thick' converter (0..0.9, default 0.4)
  // what the pack's manifest.json said about the face when it was picked (kept: shown without the pack folder)
  name?: string
  credits?: string
  credits_url?: string // http(s) only
}

/** Hair converters of fsmod.scanface.HAIR_MODES, in the order shown in the editor. */
export const HAIR_MODES = ['standard', 'volume', 'split', 'split_sharp', 'split_sharp_thick'] as const
/** Hair converter of a face picked now (the backend's scanface.NEW_FACE_HAIR_MODE); saved faces keep theirs. */
export const NEW_FACE_HAIR_MODE: HairMode = 'volume'
export type HairMode = (typeof HAIR_MODES)[number]
/** Hair converters with a strand thickness (scanface 'thick' step) and its range. */
export const THICK_HAIR_MODES: readonly HairMode[] = ['split_sharp_thick']
export const HAIR_THICKNESS = { default: 0.4, max: 0.9, step: 0.1 }

/** A face of a pack folder of the settings; name and credits only when the pack's manifest.json lists it. */
export interface FacePackFace {
  id: number
  hair: boolean
  hairlod: boolean
  photo: boolean
  folder: string // the pack folder (with id, identifies the face: the same id may exist in several packs)
  pack: string // the pack's name (its folder name)
  name?: string
  credits?: string
  credits_url?: string
}

/** A problem of a pack's manifest.json (fsmod.facepack.read_manifest). */
export interface FacePackWarning {
  code:
    | 'manifest_unreadable'
    | 'manifest_invalid_json'
    | 'manifest_wrong_type'
    | 'manifest_newer_version'
    | 'manifest_bad_entries'
    | 'manifest_bad_links'
  count?: number
  detail?: string
}

/** A pack inside a face folder of the settings: the folder itself, or one of the versions it brings side by side
 * (name "folder / version"). */
export interface FacePackSummary {
  folder: string // the pack's own folder (identifies its faces)
  root: string // the folder of the settings it was found in
  index: number // position of that folder in the list asked for
  name: string
  count: number
  warnings: FacePackWarning[]
  error: string | null // 'facepack_not_found': a folder without faces
}

export interface FacePackPage {
  total: number
  items: FacePackFace[]
  packs: FacePackSummary[]
}

export interface FacePlayer {
  name: string
  club?: string
  nationality?: string
}

/** A player of the players base (settings): what "Usar dados da base" can copy into a player of the project. */
export interface BasePlayer extends FacePlayer {
  id: number
  first_name?: string
  last_name?: string
  jersey_name?: string
  birth_date?: string // YYYY-MM-DD
  height_cm?: number
  weight_kg?: number
  preferred_foot?: 'Right' | 'Left'
  nation_id?: number // game nation matching `nationality`
  skills?: Record<string, number> // ATH..SPE (1-99) and TRI (0-4), converted from the FIFA attributes
}

/** Changes to the game's own leagues, teams and stadiums (only what differs from the game). */
export interface OriginalChanges {
  hidden_leagues?: number[]
  hidden_teams?: number[]
  team_locks?: Record<string, boolean>
  stadium_locks?: Record<string, boolean>
  /** stadiumid (a stadium or one of its country versions) -> its ball: a new Ball's uid or a game ball's id */
  stadium_balls?: Record<string, string | number>
}

/** Optional changes to the game's own scripts (fsmod.gamepatches); all off by default. */
export interface GamePatches {
  close_up_heads?: boolean // players keep the close-up head, hair and eyes at any camera distance
}

export type FriendlyMode = 'original' | 'clone'

/** A player of the World Tour friendly match. original: himself (keeps his photo, no level or skills to buy); clone: a
 * copy with a level and skills to buy, without his photo in the menus. */
export interface FriendlyPlayer {
  player: PlayerRef
  mode?: FriendlyMode
}

export interface WorldTour {
  dark?: FriendlyPlayer[]
  white?: FriendlyPlayer[]
}

export interface Project {
  version: 9
  leagues: League[]
  teams: Team[]
  players: Player[]
  boots?: Boot[]
  gloves?: Glove[]
  balls?: Ball[]
  originals?: OriginalChanges
  game_patches?: GamePatches
  world_tour?: WorldTour
}

/** Values a new player inherits from its template player where the project leaves a field unset. */
export interface PlayerDefaults {
  template: number
  template_name: string
  team: string | null // the player's new team the number/position below are for (none: only game teams)
  number: number | null
  position: number | null
  height: number
  weight: number
  birthdate: string | null
  foot: 'right' | 'left'
  nationality: number
  skills: Record<string, number>
  appearance: Record<string, number>
}

export interface Issue {
  code: string
  severity: 'error' | 'warning'
  entity: string | null
  field: string | null
  params: Record<string, unknown>
  message: string
}

export interface PatchStatus {
  folder?: string
  built: boolean
  up_to_date: boolean
  built_at?: string
  files?: string[]
}

export interface Config {
  game_dir: string | null
  save_dir: string | null
  project_dir: string
  backups_dir: string
  face_pack_dirs?: string[] // face pack folders (FIFA 14-16), one pack each, read in place
  players_base_file?: string | null // players JSON (who each EA player id is), read in place
  terms_version?: number | null // version of the first-run notice the user accepted
  build_cores?: number | null // cores the build may use (null = all but one)
  build_memory_percent?: number | null // percent of the machine's memory the build may use (null = 50)
  language?: 'pt-BR' | 'en' | null // interface language; changed only through api.saveLanguage
}

export type NotificationKind = 'error' | 'warning' | 'success' | 'info'
export type NotificationReadState = 'all' | 'read' | 'unread'

/** A message the interface showed in a toast, kept by the backend (notification center). */
export interface AppNotification {
  id: number
  kind: NotificationKind
  title: string
  description?: string | null
  created_at: string // ISO 8601
  read: boolean
  language?: string | null // interface language it was written in
  entity?: string | null // uid of the league/team/player it is about
}

export interface NewNotification {
  kind: NotificationKind
  title: string
  description?: string
  created_at?: string
  language?: string
  entity?: string
}

export interface NotificationQuery {
  offset?: number
  limit?: number
  kind?: NotificationKind
  state?: NotificationReadState
}

export interface NotificationPage {
  total: number // matching the filters
  unread: number // all unread ones
  items: AppNotification[]
}

/** The given ids, or (all) every notification matching the filters except `exclude`. */
export interface NotificationSelection {
  ids?: number[]
  all?: boolean
  kind?: NotificationKind
  state?: NotificationReadState
  exclude?: number[]
}

/** What the build may use on this machine (GET /api/machine); cores / memory_mb null when the system does not tell. */
export interface MachineInfo {
  cores: number | null
  memory_mb: number | null
  default_cores: number
  default_memory_percent: number
  memory_percent_range: [number, number] // allowed memory setting (10-90)
  worker_memory_mb: number
  workers: number
}

/** State of the first-run setup and of the game (GET /api/status → setup). */
export interface SetupState {
  required: boolean
  reasons: ('originals' | 'game_dir' | 'save_dir' | 'terms')[]
  terms_version: number
  originals: { complete: boolean; verified: boolean; missing: string[]; modified: string[] }
  game: {
    version: string | null
    tested: boolean
    tested_versions: string[]
    installed: boolean // the app's patch is in the game
    changed: string[] // installed files changed outside the app
  }
}

export interface Status {
  original_files: { folder: string; missing: string[] }
  config: Config
  setup: SetupState
  project: { path: string; exists: boolean }
  patch: PatchStatus
}

/** POST /api/setup/check: a game folder the user picked. */
export interface GameCheck {
  valid: boolean // a ReStreet root (Game/data0.big)
  version: string | null
  tested: boolean
  files: Record<string, 'ok' | 'missing' | 'different' | 'added'> // added: a mod's database (data8)
  official: boolean // the 12 files are the official ones
  app_patch: boolean // a patch installed by this app (it can undo it)
  accepted: boolean // official, or what differs is the app's own patch
  originals: SetupState['originals']
  save_dir_guess: string | null
}

export interface OriginalLeague {
  id: number
  name: string
  short_name: string | null
  sort_order: number
  country: number
  hidden: boolean
  team_count: number
}

export interface OriginalTeam {
  id: number
  name: string
  short_name: string | null
  abbreviation: string | null
  league: number | null
  player_count: number
  primary_color: RGB
  secondary_color: RGB
  generic: boolean
  captain: number // playerid of the game's captain
  takers: Record<TakerRole, number> // the game's set-piece takers
  lockable: boolean // the game can lock it (special teams)
  locked: boolean // locked in the game
  crest: boolean // has a menu crest (GET /api/originals/crests/<id>.webp); the game's internal teams have none
}

/** One row of the game's stadiums table: a stadium, or one of its country versions. region: renderingregionid
 * (1-7 = US, England, France, Italy, Germany, Spain, Canada; -1 = a stadium without versions). */
export interface StadiumVersion {
  id: number
  region: number
  ball: number // the game's ball (balltype)
  menu: boolean // hitpitchdefault: the row the game's menus list and an ordinary match loads
}

/** A stadium of the game (its rows grouped), as GET /api/originals/stadiums gives it. */
export interface OriginalStadium {
  id: number // the first row's stadiumid
  name: string
  versions: StadiumVersion[]
  in_menu: boolean // listed in the game's menus (one of its rows is flagged)
  lockable_id: number | null // the row the game can lock (the lock switch), none = always unlocked
  locked: boolean // locked in the game
  filters: number[] // match setups that offer it (Catalog.stadium_filters ids)
  surface: number
  pitch_size: number
  goal_type: number
  walls: boolean
  capacity: number
  times: number[] // times of day (1 = day, 3 and 4 = night)
  free_roam: boolean // not a match venue (adidas Z5 free roam)
}

/** A match setup (fifaStadiumFilter): which stadiums the game offers for it. */
export interface StadiumFilter {
  id: number
  numplayersonpitch: number
  goalieon: number
  isfutsal: number
  islastmanstanding: number
}

/** One player of an original team's squad as the game has it (GET /api/originals/teams/{id}/squad). */
export interface OriginalSquadLink {
  player: number
  number: number | null
  position: number | null
}

export interface OriginalPlayer {
  id: number
  first_name: string
  last_name: string
  display_name: string
  jersey_name: string | null
  teams: number[]
  number: number | null
  position: number | null
  height: number
  weight: number
  birthdate: string | null
  foot: 'right' | 'left'
  nationality: number
  generic_head: boolean
  photo: boolean // has a menu photo (GET /api/originals/photos/<id>.webp); most generic heads have none
  skills: Record<string, number>
  appearance: Record<string, number>
}

export type HairGroupKey = 'afro' | 'very_short' | 'short' | 'medium' | 'long' | 'helmets' | 'other'

export interface Catalog {
  positions: { code: number; abbr: string }[]
  nations: { id: number; name: string }[]
  appearance: Record<string, number[]>
  appearance_natural: Record<string, number[]> // what "randomize" draws from where it differs: no green hair
  hair_groups: { key: HairGroupKey; codes: number[] }[] // the game's hair categories
  skills: Record<string, { min: number; max: number }>
  template_teams: OriginalTeam[]
  max_roster: number
  max_leagues: number // new leagues (one free image number each)
  max_league_teams: number // teams of a league, new + original (team selector)
  hair_colors: Record<number, string>
  lineup_modes: LineupMode[]
  street_options: Record<StreetPartName, Record<string, number[]>> // {part: {style: [patterns]}}
  street_arms: Record<string, number> // top style -> arms mesh (long/short sleeves, tank top)
  street_full_length_bottoms: number[] // trousers: legs and socks are hidden under them
  template_street: Record<string, Partial<Record<KitKind, Record<StreetPartName, StreetSlot[]>>>>
  ranges: Record<'height' | 'weight' | 'number', [number, number]>
  boots: { street_slots: number; surface_fields: Record<ShoeSurface, string> }
  gloves: { slots: number } // free codes for new gloves
  balls: { slots: number } // free ids for new balls
  stadium_filters: StadiumFilter[]
}

export interface ImageUpload {
  path: string
}

export interface BuildResponse {
  log: string[]
  assigned_league_ids: Record<string, number>
  assigned_team_ids: Record<string, number>
  assigned_player_ids: Record<string, number>
  assigned_boot_codes: Record<string, number>
  assigned_glove_codes: Record<string, number>
  assigned_ball_codes: Record<string, number>
  cache_reused_files?: number // files of the patch that came from the build cache (real faces and kits)
  duration_s?: number // how long the build took
  patch: PatchStatus
}

/** Steps of "Gerar patch" in order (fsmod.builder.BUILD_STEPS). */
export type BuildStep = 'database' | 'leagues' | 'teams' | 'images' | 'texts' | 'files'

/** GET /api/patch/progress: the current (or last) build. */
export interface BuildProgress {
  running: boolean
  steps: BuildStep[]
  step: BuildStep | null
  done: number
  total: number
  message: string
  elapsed?: number
  error: string | null
}

export interface InstallResponse {
  backup: string | null
  installed: string[]
  restored: string[]
  removed: string[]
  save_removed: number
}

export interface UninstallResponse {
  restored: string[]
  removed: string[]
  save_removed: number
}
