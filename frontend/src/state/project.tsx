import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, bumpProjectImagesRevision } from '@/api/client'
import { lineupsWithout } from '@/lib/lineup'
import type { Issue, League, Player, PlayerDefaults, Project, Team } from '@/api/types'

const EMPTY: Project = { version: 2, leagues: [], teams: [], players: [] }
const VALIDATE_DELAY_MS = 400

export const newUid = (prefix: 'lg' | 'tm' | 'jg') =>
  `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

interface ProjectContextValue {
  loaded: boolean
  draft: Project
  dirty: boolean
  issues: Issue[]
  /** values each player inherits from its template player (per uid) */
  defaults: Record<string, PlayerDefaults>
  saving: boolean
  setDraft: (update: (p: Project) => Project) => void
  updateLeague: (uid: string, patch: Partial<League>) => void
  updateTeam: (uid: string, patch: Partial<Team>) => void
  updatePlayer: (uid: string, patch: Partial<Player>) => void
  addLeague: (league: League) => void
  addTeam: (team: Team) => void
  addPlayer: (player: Player) => void
  removeLeague: (uid: string) => void
  removeTeam: (uid: string) => void
  removePlayer: (uid: string) => void
  save: () => Promise<void>
  discard: () => void
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

const replace = <T extends { uid: string }>(list: T[], uid: string, patch: Partial<T>) =>
  list.map((e) => (e.uid === uid ? { ...e, ...patch } : e))

export function ProjectProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['project'], queryFn: api.project, staleTime: Infinity, retry: false })
  const [draft, setDraftState] = useState<Project>(EMPTY)
  const [saved, setSaved] = useState<string>(JSON.stringify(EMPTY))
  const [issues, setIssues] = useState<Issue[]>([])
  const [defaults, setDefaults] = useState<Record<string, PlayerDefaults>>({})
  const [saving, setSaving] = useState(false)
  const validateSeq = useRef(0)

  // (re)load the saved project into the draft whenever the server copy changes
  useEffect(() => {
    if (!query.data) return
    bumpProjectImagesRevision() // a reloaded project (e.g. a restored backup) may have other files under the same names
    setDraftState(query.data.project)
    setSaved(JSON.stringify(query.data.project))
    setIssues(query.data.issues)
    setDefaults(query.data.defaults)
  }, [query.data])

  const dirty = useMemo(() => JSON.stringify(draft) !== saved, [draft, saved])

  // live validation of the draft (debounced; the latest answer wins)
  useEffect(() => {
    if (!query.data || !dirty) return
    const seq = ++validateSeq.current
    const timer = setTimeout(() => {
      api
        .validate(draft)
        .then((r) => {
          if (seq !== validateSeq.current) return
          setIssues(r.issues)
          setDefaults(r.defaults)
        })
        .catch(() => undefined)
    }, VALIDATE_DELAY_MS)
    return () => clearTimeout(timer)
  }, [draft, dirty, query.data])

  // warn before closing the tab with unsaved changes
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const setDraft = useCallback((update: (p: Project) => Project) => setDraftState((p) => update(p)), [])

  const save = useCallback(async () => {
    setSaving(true)
    try {
      const r = await api.saveProject(draft)
      bumpProjectImagesRevision() // uploads now have the fixed names of the images they replaced
      setSaved(JSON.stringify(r.project))
      setDraftState(r.project)
      setIssues(r.issues)
      setDefaults(r.defaults)
      queryClient.setQueryData(['project'], { project: r.project, issues: r.issues, defaults: r.defaults })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
    } finally {
      setSaving(false)
    }
  }, [draft, queryClient])

  const value = useMemo<ProjectContextValue>(
    () => ({
      loaded: !!query.data,
      draft,
      dirty,
      issues,
      defaults,
      saving,
      setDraft,
      updateLeague: (uid, patch) => setDraft((p) => ({ ...p, leagues: replace(p.leagues, uid, patch) })),
      updateTeam: (uid, patch) => setDraft((p) => ({ ...p, teams: replace(p.teams, uid, patch) })),
      updatePlayer: (uid, patch) => setDraft((p) => ({ ...p, players: replace(p.players, uid, patch) })),
      addLeague: (league) => setDraft((p) => ({ ...p, leagues: [...p.leagues, league] })),
      addTeam: (team) => setDraft((p) => ({ ...p, teams: [...p.teams, team] })),
      addPlayer: (player) => setDraft((p) => ({ ...p, players: [...p.players, player] })),
      removeLeague: (uid) => setDraft((p) => ({ ...p, leagues: p.leagues.filter((l) => l.uid !== uid) })),
      // removing a team turns its players into free agents (they are not deleted)
      removeTeam: (uid) =>
        setDraft((p) => ({
          ...p,
          teams: p.teams.filter((t) => t.uid !== uid),
          players: p.players.map((pl) => (pl.team === uid ? { ...pl, team: null } : pl)),
        })),
      removePlayer: (uid) =>
        setDraft((p) => ({
          ...p,
          players: p.players.filter((pl) => pl.uid !== uid),
          teams: p.teams.map((t) => ({
            ...t,
            captain: t.captain === uid ? undefined : t.captain,
            lineups: lineupsWithout(t, uid),
          })),
        })),
      save,
      discard: () => {
        setDraftState(JSON.parse(saved))
        if (query.data) {
          setIssues(query.data.issues)
          setDefaults(query.data.defaults)
        }
      },
    }),
    [query.data, draft, dirty, issues, defaults, saving, setDraft, save, saved],
  )

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject must be used inside ProjectProvider')
  return ctx
}

/** Values a player inherits from its template player (undefined until the backend answers). */
export function usePlayerDefaults(uid: string | undefined): PlayerDefaults | undefined {
  const { defaults } = useProject()
  return uid ? defaults[uid] : undefined
}

/** Issues of one entity (optionally of one field). */
export function useIssues(entity: string | undefined, field?: string) {
  const { issues } = useProject()
  return useMemo(
    () => issues.filter((i) => i.entity === entity && (field === undefined || i.field === field)),
    [issues, entity, field],
  )
}
