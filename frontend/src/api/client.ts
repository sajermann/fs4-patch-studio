import type {
  BasePlayer,
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
  OriginalStadium,
  OriginalTeam,
  PatchStatus,
  PlayerDefaults,
  Project,
  RGB,
  ScannedFace,
  Status,
} from './types'
import { hasMessage, translate } from '@/i18n'

/** Text of a backend error in the interface language: by its code (and `reason`) when the app knows it, else the
 * backend's own (pt-BR) message. */
function errorText(status: number, detail: unknown, d: Record<string, unknown>) {
  const key = `apiError.${d.code}${typeof d.reason === 'string' ? '.' + d.reason : ''}`
  if (typeof d.code === 'string' && hasMessage(key)) return translate(key)
  if (typeof d.message === 'string') return d.message
  return typeof detail === 'string' ? detail : translate('apiError.status', { status })
}

/** Error returned by the backend; `message` is in the interface language when the app knows the error code. */
export class ApiError extends Error {
  status: number
  code?: string
  issues?: Issue[]

  constructor(status: number, detail: unknown) {
    const d = typeof detail === 'object' && detail !== null ? (detail as Record<string, unknown>) : {}
    super(errorText(status, detail, d))
    this.status = status
    this.code = typeof d.code === 'string' ? d.code : undefined
    this.issues = Array.isArray(d.issues) ? (d.issues as Issue[]) : undefined
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = (await res.json()).detail
    } catch {
      /* body is not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
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

  project: () => request<{ project: Project; issues: Issue[]; defaults: Record<string, PlayerDefaults> }>('/api/project'),
  /** Replaces the project with a backup zip (database.json + images + faces). */
  restoreBackup: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ project: Project; issues: Issue[]; defaults: Record<string, PlayerDefaults> }>('/api/project/restore', {
      method: 'POST',
      body: form,
    })
  },
  saveProject: (project: Project) =>
    request<{ project: Project; issues: Issue[]; defaults: Record<string, PlayerDefaults>; patch: PatchStatus }>(
      '/api/project',
      json('PUT', project),
    ),
  validate: (project: Project) =>
    request<{ issues: Issue[]; defaults: Record<string, PlayerDefaults> }>('/api/project/validate', json('POST', project)),

  originalLeagues: () => request<OriginalLeague[]>('/api/originals/leagues'),
  originalTeams: () => request<OriginalTeam[]>('/api/originals/teams'),
  originalStadiums: () => request<OriginalStadium[]>('/api/originals/stadiums'),
  originalPlayers: (params: { team?: number; q?: string; offset?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return request<{ total: number; items: OriginalPlayer[] }>(`/api/originals/players?${qs}`)
  },
  catalog: () => request<Catalog>('/api/catalog'),

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
export const originalPhotoUrl = (playerid: number) => `/api/originals/photos/${playerid}.webp`

/** Player photo as the game shows it (square crop). */
export const photoPreviewUrl = (path: string) => withRevision(`/api/preview/photo.png?${new URLSearchParams({ path })}`)

export const kitPreviewUrl = (jersey: RGB, crest?: string) => {
  const qs = new URLSearchParams({ jersey: jersey.join(',') })
  if (!crest) return `/api/preview/kit.png?${qs}`
  qs.set('crest', crest)
  return withRevision(`/api/preview/kit.png?${qs}`)
}

/** Kit texture for the 3D preview: a real kit PNG of the project, or the solid color + crest decal. */
export const kitTextureUrl = (part: 'jersey' | 'shorts', kit: { jersey: RGB; shorts: RGB; crest?: string | null; real?: { jersey: string; shorts: string } }) => {
  if (kit.real) return withRevision(`/api/preview/real-kit/${part}.png?${new URLSearchParams({ image: kit.real[part] })}`)
  const qs = new URLSearchParams({ color: kit[part].join(',') })
  if (!kit.crest) return `/api/preview/kit/${part}.png?${qs}`
  qs.set('crest', kit.crest)
  return withRevision(`/api/preview/kit/${part}.png?${qs}`)
}

/** Where a real face is read from: a pack folder (not picked yet) or the project (player uid). */
export type FaceSource = { folder: string; face: number } | { player: string; face: number }

const faceQuery = (source: FaceSource) =>
  new URLSearchParams('folder' in source ? { folder: source.folder, face: String(source.face) } : { player: source.player, face: String(source.face) })

/** Front render of a face, for the gallery. */
export const faceThumbUrl = (source: FaceSource) => `/api/facepack/thumb.png?${faceQuery(source)}`


/** Query of the converted face's preview files (/api/preview/scanned/<file>). */
export const scannedFaceQuery = (source: FaceSource, haircolorcode: number, paintScalp = true) => {
  const qs = faceQuery(source)
  qs.set('haircolor', String(haircolorcode))
  if (!paintScalp) qs.set('paint', 'false')
  return qs.toString()
}
