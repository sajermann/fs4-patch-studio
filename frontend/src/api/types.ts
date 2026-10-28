// Mirrors core/fsmod/model.py (contract v2) and the backend responses.

export type RGB = [number, number, number]
export type KitKind = 'home' | 'away'
export type KitPart = 'jersey' | 'shorts' | 'socks'
export type RealKitSlot = 'home' | 'away' | 'goalkeeper'
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
}

export interface League {
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
}

export interface Team {
  uid: string
  name: string
  league: number | string // new league uid or original league id
  primary_color: RGB
  secondary_color: RGB
  team_id?: number | null // teamid in the game, given by the build
  short_name?: string
  name_10?: string
  name_7?: string
  abbreviation?: string
  crest?: string
  kits: Partial<Record<KitKind, Partial<Record<KitPart, RGB>>>>
  street_kits?: Partial<Record<KitKind, StreetKit>>
  use_real_kits?: boolean // team kits from real_kits instead of solid color + crest
  real_kits?: Partial<Record<RealKitSlot, RealKit>>
  template: number
  captain?: string
  lineups?: Lineup[] // starting lineup per game mode; a mode without one = the game's pick
  hidden?: boolean // left out of the patch (with its players)
}

/** Starting lineup of one game mode (fs4lineup); it seeds a new save. */
export interface Lineup {
  players: number // 1-6
  goalkeeper: boolean
  tactic: number // 0 static, 1 dynamic, 2 street (only 5 and 6 players have 0 and 2)
  starters: (string | null)[] // player uid per slot; null = filled by the build
  reserves: string[] // bench order; players left out follow in roster order
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

/** Street Home/Away; a missing part keeps the template's pieces. */
export type StreetKit = Partial<Record<StreetPartName, StreetPiece>>

export interface Player {
  uid: string
  first_name: string
  last_name: string
  player_id?: number | null // playerid in the game, given by the build
  team?: string | null
  generic: boolean
  display_name?: string
  jersey_name?: string
  number?: number
  position?: number
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
  hidden?: boolean // left out of the patch (its id stays reserved)
}

/** Real face from a FIFA 14 pack; its files are copied into the project (faces/<player uid>/). */
export interface ScannedFace {
  source_id: number
  pack?: string
  paint_scalp?: boolean // hair color painted on the scalp by the converter (default true)
  hair_mode?: HairMode // hair converter (default 'standard')
  hair_thickness?: number // strand thickness of the 'split_sharp_thick' converter (0..0.9, default 0.4)
}

/** Hair converters of fsmod.scanface.HAIR_MODES, in the order shown in the editor. */
export const HAIR_MODES = ['standard', 'volume', 'split', 'split_sharp', 'split_sharp_thick'] as const
export type HairMode = (typeof HAIR_MODES)[number]
/** Hair converters with a strand thickness (scanface 'thick' step) and its range. */
export const THICK_HAIR_MODES: readonly HairMode[] = ['split_sharp_thick']
export const HAIR_THICKNESS = { default: 0.4, max: 0.9, step: 0.1 }

export interface FacePackFace {
  id: number
  hair: boolean
  hairlod: boolean
  photo: boolean
  player: FacePlayer | null // who the face is (EA players base, by id); null when the base does not know the id
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

export interface FacePack {
  folder: string
  name: string
  faces: FacePackFace[]
}

/** Changes to the game's own leagues, teams and stadiums (only what differs from the game). */
export interface OriginalChanges {
  hidden_leagues?: number[]
  hidden_teams?: number[]
  team_locks?: Record<string, boolean>
  stadium_locks?: Record<string, boolean>
}

/** Optional changes to the game's own scripts (fsmod.gamepatches); all off by default. */
export interface GamePatches {
  close_up_heads?: boolean // players keep the close-up head, hair and eyes at any camera distance
}

export interface Project {
  version: 2
  leagues: League[]
  teams: Team[]
  players: Player[]
  originals?: OriginalChanges
  game_patches?: GamePatches
}

/** Values a new player inherits from its template player where the project leaves a field unset. */
export interface PlayerDefaults {
  template: number
  template_name: string
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
  face_pack_dir?: string | null
  players_base_file?: string | null // players JSON (who each EA player id is), read in place
  terms_version?: number | null // version of the first-run notice the user accepted
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
  lockable: boolean // the game can lock it (special teams)
  locked: boolean // locked in the game
  crest: boolean // has a menu crest (GET /api/originals/crests/<id>.webp); the game's internal teams have none
}

export interface OriginalStadium {
  id: number
  name: string
  locked: boolean
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

export interface Catalog {
  positions: { code: number; abbr: string }[]
  nations: { id: number; name: string }[]
  appearance: Record<string, number[]>
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
  template_street: Record<string, Partial<Record<KitKind, Record<StreetPartName, { style: number; pattern: number }>>>>
  ranges: Record<'height' | 'weight' | 'number', [number, number]>
}

export interface ImageUpload {
  path: string
}

export interface BuildResponse {
  log: string[]
  assigned_league_ids: Record<string, number>
  assigned_team_ids: Record<string, number>
  assigned_player_ids: Record<string, number>
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
