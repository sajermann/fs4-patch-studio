import type { PreviewKit } from '@/components/common/PlayerPreview'
import type {
  BasePlayer,
  Boot,
  BootImport,
  Ball,
  BallImport,
  Glove,
  GloveImport,
  OriginalBoot,
  OriginalBall,
  OriginalGlove,
  League,
  BuildProgress,
  BuildResponse,
  GameCheck,
  Catalog,
  Config,
  FacePack,
  FacePlayer,
  ImageUpload,
  InstallResponse,
  SetupState,
  UninstallResponse,
  Issue,
  OriginalLeague,
  OriginalPlayer,
  OriginalSquadLink,
  OriginalStadium,
  OriginalTeam,
  Player,
  Team,
  PatchStatus,
  PlayerDefaults,
  Project,
  RGB,
  ScannedFace,
  ShareInspect,
  ShareKind,
  Status,
} from './types'
import { hasMessage, translate } from '@/i18n'

/** Text of a backend error in the interface language: by its code (and `reason`) when the app knows it, else the
 * backend's own (pt-BR) message. */
function errorText(status: number, detail: unknown, d: Record<string, unknown>) {
  const key = `apiError.${d.code}${typeof d.reason === 'string' ? '.' + d.reason : ''}`
  if (typeof d.code === 'string' && hasMessage(key)) return translate(key, d)
  if (typeof d.message === 'string') return d.message
  return typeof detail === 'string' ? detail : translate('apiError.status', { status })
}

/** Error returned by the backend; `message` is in the interface language when the app knows the error code, followed
 * by the technical text (`error`) when there is one. Status 0: the backend did not answer. */
export class ApiError extends Error {
  status: number
  code?: string
  issues?: Issue[]
  /** the message without the technical text */
  summary: string
  /** unexpected errors (`internal_error`, files, project file): the exception text, the file it was about and the
   * backend log file (desktop app) */
  error?: string
  path?: string
  logFile?: string

  constructor(status: number, detail: unknown) {
    const d = typeof detail === 'object' && detail !== null ? (detail as Record<string, unknown>) : {}
    const summary = errorText(status, detail, d)
    const error = typeof d.error === 'string' ? d.error : undefined
    super(error && !summary.includes(error) ? `${summary} (${error})` : summary)
    this.summary = summary
    this.status = status
    this.code = typeof d.code === 'string' ? d.code : undefined
    this.issues = Array.isArray(d.issues) ? (d.issues as Issue[]) : undefined
    this.error = error
    this.path = typeof d.path === 'string' ? d.path : undefined
    this.logFile = typeof d.log_file === 'string' ? d.log_file : undefined
  }
}

async function send(path: string, init?: RequestInit) {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (e) {
    // the backend is not running (closed, crashed) or the connection dropped
    throw new ApiError(0, { code: 'backend_unreachable', error: e instanceof Error ? e.message : String(e) })
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = (await res.json()).detail
    } catch {
      /* body is not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  status: () => request<Status>('/api/status'),
  config: () => request<Config>('/api/config'),
  saveConfig: (config: Config) => request<Config>('/api/config', json('PUT', config)),

  project: () => request<{ project: Project; issues: Issue[]; defaults: Record<string, PlayerDefaults>; untouched: string[]; changed_squads: number[]; changed_leagues: number[] }>('/api/project'),
  /** Replaces the project with a backup zip (database.json + images + faces). */
  restoreBackup: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ project: Project; issues: Issue[]; defaults: Record<string, PlayerDefaults>; untouched: string[]; changed_squads: number[]; changed_leagues: number[] }>('/api/project/restore', {
      method: 'POST',
      body: form,
    })
  },
  saveProject: (project: Project) =>
    request<{ project: Project; issues: Issue[]; defaults: Record<string, PlayerDefaults>; untouched: string[]; changed_squads: number[]; changed_leagues: number[]; patch: PatchStatus }>(
      '/api/project',
      json('PUT', project),
    ),
  validate: (project: Project) =>
    request<{ issues: Issue[]; defaults: Record<string, PlayerDefaults>; untouched: string[]; changed_squads: number[]; changed_leagues: number[] }>('/api/project/validate', json('POST', project)),

  /** Players that complete the roster of a new team of the draft; the caller adds them to the draft. */
  generatePlayers: (team: string, project: Project) => request<Player[]>(`/api/teams/${team}/generate-players`, json('POST', project)),

  originalLeagues: () => request<OriginalLeague[]>('/api/originals/leagues'),
  originalTeams: () => request<OriginalTeam[]>('/api/originals/teams'),
  originalStadiums: () => request<OriginalStadium[]>('/api/originals/stadiums'),
  originalPlayers: (params: { team?: number; q?: string; offset?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return request<{ total: number; items: OriginalPlayer[] }>(`/api/originals/players?${qs}`)
  },
  /** Starts editing an original team: its crest and kits become project images; returns the filled Team. */
  editOriginalLeague: (leagueid: number, uid: string) =>
    request<League>(`/api/originals/leagues/${leagueid}/edit?${new URLSearchParams({ uid })}`, { method: 'POST' }),
  editOriginalTeam: (teamid: number, uid: string) =>
    request<Team>(`/api/originals/teams/${teamid}/edit?${new URLSearchParams({ uid })}`, { method: 'POST' }),
  /** The game's own squad of an original team (restoring it puts this squad back). */
  originalSquad: (teamid: number) => request<OriginalSquadLink[]>(`/api/originals/teams/${teamid}/squad`),
  /** Starts editing one of the game's players: his photo becomes a project image; returns the filled Player. */
  editOriginalPlayer: (playerid: number, uid: string) =>
    request<Player>(`/api/originals/players/${playerid}/edit?${new URLSearchParams({ uid })}`, { method: 'POST' }),
  catalog: () => request<Catalog>('/api/catalog'),

  /** The game's own boots. */
  originalBoots: () => request<OriginalBoot[]>('/api/originals/boots'),
  /** Starts editing one of the game's boots: the entry without files of its own (the game's stay). */
  editOriginalBoot: (code: number, uid: string) =>
    request<Boot>(`/api/originals/boots/${code}/edit?${new URLSearchParams({ uid })}`, { method: 'POST' }),
  /** A boot's pack file (checked) or picture, under a provisional name until the project is saved. */
  uploadBootFile: (kind: 'mesh' | 'texture', file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>(`/api/boots/files?kind=${kind}`, { method: 'POST', body: form })
  },
  uploadBootThumbnail: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>('/api/boots/thumbnail', { method: 'POST', body: form })
  },
  /** Boots of a shared zip; nothing is saved (one boot fills the form, many are added by the caller). */
  importBoots: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<BootImport>('/api/boots/import', { method: 'POST', body: form })
  },
  /** Zip of saved boots to share: { file name, contents }. */
  exportBoots: async (uids: string[], many = false) => {
    const res = await send('/api/boots/export', json('POST', { uids, many }))
    const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'boots.zip'
    return { name, blob: await res.blob() }
  },

  /** What a shared zip of leagues, teams or players holds; nothing changes in the project. */
  inspectShare: <T>(kind: ShareKind, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ShareInspect<T>>(`/api/share/${kind}/inspect`, { method: 'POST', body: form })
  },
  /** The chosen entries of an inspected zip, their files put into the project; the caller merges them and saves. */
  applyShare: <T>(kind: ShareKind, token: string, uids: string[], asUids: Record<string, string> = {}) =>
    request<{ items: T[] }>(`/api/share/${kind}/apply`, json('POST', { token, uids, as_uids: asUids })),
  /** Zip of saved leagues, teams or players to share: { file name, contents }. */
  exportShare: async (kind: ShareKind, uids: string[]) => {
    const res = await send(`/api/share/${kind}/export`, json('POST', { uids }))
    const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? `${kind}.zip`
    return { name, blob: await res.blob() }
  },

  /** The game's own balls. */
  originalBalls: () => request<OriginalBall[]>('/api/originals/balls'),
  /** Starts editing one of the game's balls: the entry without files of its own (the game's stay). */
  editOriginalBall: (id: number, uid: string) =>
    request<Ball>(`/api/originals/balls/${id}/edit?${new URLSearchParams({ uid })}`, { method: 'POST' }),
  /** A ball's pack file (checked; kind: mesh or texture) under a provisional name until the project is saved. */
  uploadBallFile: (kind: 'mesh' | 'texture', file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>(`/api/balls/files?${new URLSearchParams({ kind })}`, { method: 'POST', body: form })
  },
  uploadBallThumbnail: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>('/api/balls/thumbnail', { method: 'POST', body: form })
  },
  /** Balls of a shared zip; nothing is saved (one ball fills the form, many are added by the caller). */
  importBalls: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<BallImport>('/api/balls/import', { method: 'POST', body: form })
  },
  /** Zip of saved balls to share: { file name, contents }. */
  exportBalls: async (uids: string[], many = false) => {
    const res = await send('/api/balls/export', json('POST', { uids, many }))
    const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'balls.zip'
    return { name, blob: await res.blob() }
  },

  /** The game's own goalkeeper gloves. */
  originalGloves: () => request<OriginalGlove[]>('/api/originals/gloves'),
  /** Starts editing one of the game's gloves: the entry without a file of its own (the game's stays). */
  editOriginalGlove: (code: number, uid: string) =>
    request<Glove>(`/api/originals/gloves/${code}/edit?${new URLSearchParams({ uid })}`, { method: 'POST' }),
  /** A glove's pack file (checked) or picture, under a provisional name until the project is saved. */
  uploadGloveFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>('/api/gloves/files', { method: 'POST', body: form })
  },
  uploadGloveThumbnail: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>('/api/gloves/thumbnail', { method: 'POST', body: form })
  },
  /** Gloves of a shared zip; nothing is saved (one glove fills the form, many are added by the caller). */
  importGloves: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<GloveImport>('/api/gloves/import', { method: 'POST', body: form })
  },
  /** Zip of saved gloves to share: { file name, contents }. */
  exportGloves: async (uids: string[], many = false) => {
    const res = await send('/api/gloves/export', json('POST', { uids, many }))
    const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'gloves.zip'
    return { name, blob: await res.blob() }
  },

  /** Provisional path until the project is saved, when the image gets the fixed name of its entity. */
  uploadImage: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageUpload>('/api/images', { method: 'POST', body: form })
  },
  /** Faces of the FIFA 14 pack folder of the settings (read in place), or of `folder` (checking it before saving). */
  facePack: (folder?: string) => request<FacePack>(`/api/facepack${folder ? `?${new URLSearchParams({ folder })}` : ''}`),
  /** Opens the Windows folder picker on this machine; null when cancelled. */
  browseFacePack: () => request<{ folder: string | null }>('/api/facepack/browse', { method: 'POST' }),
  /** Copies one face of the pack into the project (faces/<player uid>/). */
  checkScannedFace: (query: string) => request<{ ok: boolean }>(`/api/preview/scanned-check?${query}`),
  /** Game hair color closest to a real face's own hair (suggested for the player), null for a face without hair. */
  faceHairColor: (source: FaceSource) =>
    request<{ haircolorcode: number | null }>(`/api/facepack/hair-color?${faceQuery(source)}`),
  pickFace: (folder: string, faceId: number, player: string) =>
    request<{ face: ScannedFace }>('/api/facepack/use', json('POST', { folder, face_id: faceId, player })),
  /** Copies a player's real face files to another player of the project (copy of a player). */
  copyFace: (fromPlayer: string, toPlayer: string, faceId: number) =>
    request<{ ok: true }>('/api/faces/copy', json('POST', { from_player: fromPlayer, to_player: toPlayer, face_id: faceId })),
  buildPatch: () => request<BuildResponse>('/api/patch/build', { method: 'POST' }),
  buildProgress: () => request<BuildProgress>('/api/patch/progress'),
  installPatch: () => request<InstallResponse>('/api/patch/install', { method: 'POST' }),
  uninstallPatch: () => request<UninstallResponse>('/api/patch/uninstall', { method: 'POST' }),
  /** Opens the Windows "save as" dialog on this machine; path null when cancelled. */
  exportPatch: () => request<{ path: string | null; files?: number }>('/api/patch/export', { method: 'POST' }),
  deleteSave: () => request<{ removed: number }>('/api/save/delete', { method: 'POST' }),

  /** Plain-text support report: machine, settings, project, patch and the end of the log files. */
  logsReport: async () => (await send('/api/logs/report')).text(),
  /** Opens the log folder in the Windows Explorer (404 `logs_not_found` in development, which logs to the console). */
  openLogs: () => request<{ folder: string }>('/api/logs/open', { method: 'POST' }),

  setupCheck: (gameDir: string) => request<GameCheck>('/api/setup/check', json('POST', { game_dir: gameDir })),
  setupApply: (setup: { game_dir: string; save_dir: string; face_pack_dir: string | null; terms_version: number }) =>
    request<{ imported: string[]; setup: SetupState }>('/api/setup/apply', json('POST', setup)),
  /** Checks a players JSON against the contract (usable players, skipped records, first problems). */
  checkPlayersBase: (file: string) =>
    request<{ players: number; skipped: number; problems: string[] }>('/api/players-base/check', json('POST', { file })),
  searchPlayersBase: (q: string) =>
    request<{ total: number; items: (FacePlayer & { id: number })[] }>(`/api/players-base/players?${new URLSearchParams({ q })}`),
  playersBaseRecord: (id: number) => request<BasePlayer>(`/api/players-base/players/${id}`),
  browsePlayersBase: () => request<{ file: string | null }>('/api/players-base/browse', { method: 'POST' }),
  /** Opens the Windows folder picker on this machine; null when cancelled. */
  browseFolder: (initial?: string | null) =>
    request<{ folder: string | null }>(`/api/dialog/folder${initial ? `?${new URLSearchParams({ initial })}` : ''}`, {
      method: 'POST',
    }),
}

// Saving gives every upload the fixed name of its entity (the same path as the image it replaced) and restoring a
// backup replaces files: URLs of project images carry this revision, bumped then, so neither the browser nor the 3D
// preview's texture cache shows the old picture under a reused path.
let imagesRevision = 0
export const projectImagesRevision = () => imagesRevision
export const bumpProjectImagesRevision = () => {
  imagesRevision += 1
}
const withRevision = (url: string) => `${url}${url.includes('?') ? '&' : '?'}r=${imagesRevision}`

/** URL of a project image (path as stored in the project, e.g. "images/x.png"). */
export const imageUrl = (path: string) => withRevision(`/api/${path}`)

/** Menu crest / photo of an original team / player (read from the originals, 128 px). */
export const originalCrestUrl = (teamid: number) => `/api/originals/crests/${teamid}.webp`
export const originalLeagueImageUrl = (leagueid: number) => `/api/originals/league-images/${leagueid}.webp`
export const originalPhotoUrl = (playerid: number) => `/api/originals/photos/${playerid}.webp`

/** The game's picture of a generic appearance code (variant: the color of a hair or beard style). */
export const appearanceThumbUrl = (field: string, code: number, variant = 0) =>
  `/api/originals/appearance/${field}/${code}.webp?variant=${variant}&v=2` // v: new pictures past the browser's cache

/** List picture of one of the game's boots. */
export const originalBootThumbUrl = (code: number) => `/api/originals/boots/${code}.webp`

/** List picture of a project boot: its own picture, or the boot drawn from its files (none: no picture yet). */
export const bootThumbUrl = (boot: Pick<Boot, 'thumbnail' | 'mesh' | 'texture'>) =>
  boot.thumbnail
    ? withRevision(`/api/boots/thumb.webp?${new URLSearchParams({ image: boot.thumbnail })}`)
    : boot.mesh && boot.texture
      ? withRevision(`/api/boots/thumb.webp?${new URLSearchParams({ mesh: boot.mesh, texture: boot.texture })}`)
      : undefined

/** The 3D preview's mesh and texture of a project boot (converted as the game wears it). */
export const bootPreviewUrls = (mesh: string, texture: string) => {
  const qs = new URLSearchParams({ mesh, texture })
  return { glb: withRevision(`/api/preview/boot.glb?${qs}`), texture: withRevision(`/api/preview/boot.png?${qs}`) }
}

/** List picture of one of the game's balls. */
export const originalBallThumbUrl = (id: number) => `/api/originals/balls/${id}.webp`

/** List picture of a project ball: its own picture, or the ball drawn from its files (none: no picture yet). */
export const ballThumbUrl = (ball: Pick<Ball, 'thumbnail' | 'mesh' | 'texture'>) =>
  ball.thumbnail
    ? withRevision(`/api/balls/thumb.webp?${new URLSearchParams({ image: ball.thumbnail })}`)
    : ball.mesh && ball.texture
      ? withRevision(`/api/balls/thumb.webp?${new URLSearchParams({ mesh: ball.mesh, texture: ball.texture })}`)
      : undefined

/** The 3D preview's mesh and texture of a project ball (converted as the game will show it). */
export const ballPreviewUrls = (mesh: string, texture: string) => {
  const qs = new URLSearchParams({ mesh, texture })
  return { glb: withRevision(`/api/preview/ball.glb?${qs}`), texture: withRevision(`/api/preview/ball.png?${qs}`) }
}

/** The 3D preview's mesh and texture of one of the game's balls. */
export const gameBallPreviewUrls = (id: number) => ({ glb: `/api/preview/ball/${id}.glb`, texture: `/api/preview/ball/${id}.png` })

/** List picture of one of the game's gloves. */
export const originalGloveThumbUrl = (code: number) => `/api/originals/gloves/${code}.webp`

/** List picture of a project glove: its own picture, or the glove drawn from its file (none: no picture yet). */
export const gloveThumbUrl = (glove: Pick<Glove, 'thumbnail' | 'texture'>) =>
  glove.thumbnail
    ? withRevision(`/api/gloves/thumb.webp?${new URLSearchParams({ image: glove.thumbnail })}`)
    : glove.texture
      ? withRevision(`/api/gloves/thumb.webp?${new URLSearchParams({ texture: glove.texture })}`)
      : undefined

/** Color map of a project glove as the game will show it (the 3D preview's texture). */
export const glovePreviewUrl = (texture: string) => withRevision(`/api/preview/glove.png?${new URLSearchParams({ texture })}`)

/** Color map of one of the game's gloves. */
export const gameGlovePreviewUrl = (code: number) => `/api/preview/glove/${code}.png`

/** Saves a downloaded file (blob) with its name. */
export function saveBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Player photo as the game shows it (square crop). */
export const photoPreviewUrl = (path: string) => withRevision(`/api/preview/photo.png?${new URLSearchParams({ path })}`)

export const kitPreviewUrl = (jersey: RGB, crest?: string) => {
  const qs = new URLSearchParams({ jersey: jersey.join(',') })
  if (!crest) return `/api/preview/kit.png?${qs}`
  qs.set('crest', crest)
  return withRevision(`/api/preview/kit.png?${qs}`)
}

/** Kit texture for the 3D preview: a real kit PNG of the project, or the solid color + crest decal. */
export const kitTextureUrl = (part: 'jersey' | 'shorts', kit: PreviewKit) => {
  if (kit.real) {
    const qs = new URLSearchParams({ image: kit.real[part] })
    const p = kit.real.print
    if (p && (p.number != null || p.name)) {
      if (p.number != null) qs.set('number', String(p.number))
      if (p.name) qs.set('name', p.name)
      qs.set('team', String(p.team))
      qs.set('kind', String(p.kind))
      qs.set('name_color', p.name_color.join(','))
      qs.set('number_color', String(p.number_color))
      qs.set('shorts_number_color', String(p.shorts_number_color))
      qs.set('front', String(p.front))
      qs.set('shorts_number', String(p.shorts_number))
      qs.set('jersey', kit.real.jersey)
      if (p.loaded) qs.set('loaded', p.loaded)
    }
    return withRevision(`/api/preview/real-kit/${part}.png?${qs}`)
  }
  const qs = new URLSearchParams({ color: kit[part].join(',') })
  if (!kit.crest) return `/api/preview/kit/${part}.png?${qs}`
  qs.set('crest', kit.crest)
  return withRevision(`/api/preview/kit/${part}.png?${qs}`)
}

/** Crest decal over a street piece for the 3D preview (transparent when the pattern carries no crest). */
export const streetCrestUrl = (part: 'top' | 'bottom' | 'socks', style: number, pattern: number, crest: string) =>
  withRevision(`/api/preview/street/${part}/${style}/${pattern}/crest.png?${new URLSearchParams({ crest })}`)

/** Where a real face is read from: a pack folder (not picked yet) or the project (player uid). */
export type FaceSource = { folder: string; face: number } | { player: string; face: number }

const faceQuery = (source: FaceSource) =>
  new URLSearchParams('folder' in source ? { folder: source.folder, face: String(source.face) } : { player: source.player, face: String(source.face) })

/** Front render of a face, for the gallery. */
export const faceThumbUrl = (source: FaceSource) => `/api/facepack/thumb.png?${faceQuery(source)}`


/** Query of the converted face's preview files (/api/preview/scanned/<file>). */
export const scannedFaceQuery = (source: FaceSource, haircolorcode: number, paintScalp = true, hairMode = 'standard', hairThickness?: number) => {
  const qs = faceQuery(source)
  qs.set('haircolor', String(haircolorcode))
  if (!paintScalp) qs.set('paint', 'false')
  if (hairMode !== 'standard') qs.set('hair', hairMode)
  if (hairThickness !== undefined) qs.set('thick', String(hairThickness))
  return qs.toString()
}
