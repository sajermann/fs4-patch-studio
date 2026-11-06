import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, bumpProjectImagesRevision } from '@/api/client'
import { LoadError } from '@/components/layout/LoadError'
import { useI18n } from '@/i18n'
import { lineupsWithout, takersWithout } from '@/lib/lineup'
import { linkOf, teamsWithout } from '@/lib/players'
import type { Boot, Issue, League, OriginalSquadLink, Player, PlayerDefaults, Project, Team } from '@/api/types'

const EMPTY: Project = { version: 6, leagues: [], teams: [], players: [], boots: [] }
const VALIDATE_DELAY_MS = 400

/** A new entry's uid: starts with a letter (never all digits, the addresses of the game's teams/players). */
export const newUid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

interface ProjectContextValue {
  loaded: boolean
  /** the project being edited plus the originals only opened (see `opened`) */
  draft: Project
  dirty: boolean
  issues: Issue[]
  /** values each player inherits from its template player (per uid) */
  defaults: Record<string, PlayerDefaults>
  /** uids of original team/player entries still exactly as loaded from the game (shown as originals; saving drops them) */
  untouched: Set<string>
  /** the game's teams whose squad the project changes (a player left/joined/changed number or position): edited too */
  changedSquads: Set<number>
  /** the game's leagues whose teams the project changes (a team joined or left): edited too */
  changedLeagues: Set<number>
  /** uids of original leagues/teams/players opened from the game but not changed: in `draft` for the pages, out of the
   * project (not saved, not validated, not "unsaved changes") until something of theirs changes */
  opened: Set<string>
  saving: boolean
  setDraft: (update: (p: Project) => Project) => void
  updateLeague: (uid: string, patch: Partial<League>) => void
  updateTeam: (uid: string, patch: Partial<Team>) => void
  updatePlayer: (uid: string, patch: Partial<Player>) => void
  updateBoot: (uid: string, patch: Partial<Boot>) => void
  addLeague: (league: League) => void
  addTeam: (team: Team) => void
  addPlayer: (player: Player) => void
  addBoots: (boots: Boot[]) => void
  /** an original league/team/player/boot loaded from the game, shown as it is until something changes (see `opened`) */
  openOriginal: (entry: { league: League } | { team: Team } | { player: Player } | { boot: Boot }) => void
  removeLeague: (uid: string) => void
  removeTeam: (uid: string, squad?: OriginalSquadLink[]) => void
  removePlayer: (uid: string) => void
  /** deleting new boots also takes them off the players wearing them; an edited game boot goes back to the game's */
  removeBoots: (uids: string[]) => void
  /** takes a new boot off players (all of them by default): each one is back to the game boot he had on those
   * surfaces, or his default */
  takeOffBoot: (uid: string, players?: string[]) => void
  save: () => Promise<void>
  discard: () => void
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

const replace = <T extends { uid: string }>(list: T[], uid: string, patch: Partial<T>) =>
  list.map((e) => (e.uid === uid ? { ...e, ...patch } : e))

interface Opened {
  leagues: League[]
  teams: Team[]
  players: Player[]
  boots: Boot[]
}
/** The project with the boots `gone` taken off its players (only `players`, when given). */
const takeOff = (p: Project, gone: Set<string>, players?: Set<string>): Project => ({
  ...p,
  players: p.players.map((pl) =>
    (!players || players.has(pl.uid)) && pl.boots && Object.values(pl.boots).some((u) => u && gone.has(u))
      ? { ...pl, boots: Object.fromEntries(Object.entries(pl.boots).filter(([, u]) => !u || !gone.has(u))) }
      : pl,
  ),
})

const NONE: Opened ={ leagues: [], teams: [], players: [], boots: [] }

const withOpened = (draft: Project, opened: Opened): Project =>
  opened.leagues.length || opened.teams.length || opened.players.length || opened.boots.length
    ? {
        ...draft,
        leagues: [...draft.leagues, ...opened.leagues],
        teams: [...draft.teams, ...opened.teams],
        players: [...draft.players, ...opened.players],
        boots: [...(draft.boots ?? []), ...opened.boots],
      }
    : draft

/** Splits an updated view (project + opened originals) back: an opened entry the update left as it was (same
 * object) stays opened; a changed one joins the project; a removed one is gone. */
function splitOpened(next: Project, opened: Opened): { draft: Project; opened: Opened } {
  const split = <T extends { uid: string }>(list: T[], mine: T[]) => {
    const same = new Set(mine.filter((e) => list.includes(e)))
    return { project: list.filter((e) => !same.has(e)), opened: mine.filter((e) => same.has(e)) }
  }
  const leagues = split(next.leagues, opened.leagues)
  const teams = split(next.teams, opened.teams)
  const players = split(next.players, opened.players)
  const boots = split(next.boots ?? [], opened.boots)
  return {
    draft: { ...next, leagues: leagues.project, teams: teams.project, players: players.project, boots: boots.project },
    opened: { leagues: leagues.opened, teams: teams.opened, players: players.opened, boots: boots.opened },
  }
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  // its error is the LoadError page below
  const query = useQuery({ queryKey: ['project'], queryFn: api.project, staleTime: Infinity, retry: false, meta: { errorShown: true } })
  const [state, setState] = useState<{ draft: Project; opened: Opened }>({ draft: EMPTY, opened: NONE })
  const draft = state.draft // the project itself (saved, validated, compared for "unsaved changes")
  const setDraftState = useCallback((d: Project) => setState((s) => ({ ...s, draft: d })), [])
  const view = useMemo(() => withOpened(state.draft, state.opened), [state])
  const openedUids = useMemo(
    () =>
      new Set([...state.opened.leagues, ...state.opened.teams, ...state.opened.players, ...state.opened.boots].map((e) => e.uid)),
    [state.opened],
  )
  const [saved, setSaved] = useState<string>(JSON.stringify(EMPTY))
  const [issues, setIssues] = useState<Issue[]>([])
  const [defaults, setDefaults] = useState<Record<string, PlayerDefaults>>({})
  const [untouched, setUntouched] = useState<Set<string>>(new Set())
  const [changedSquads, setChangedSquads] = useState<Set<number>>(new Set())
  const [changedLeagues, setChangedLeagues] = useState<Set<number>>(new Set())
  const [saving, setSaving] = useState(false)
  const validateSeq = useRef(0)

  // (re)load the saved project into the draft whenever the server copy changes
  useEffect(() => {
    if (!query.data) return
    bumpProjectImagesRevision() // a reloaded project (e.g. a restored backup) may have other files under the same names
    setState({ draft: query.data.project, opened: NONE })
    setSaved(JSON.stringify(query.data.project))
    setIssues(query.data.issues)
    setDefaults(query.data.defaults)
    setUntouched(new Set(query.data.untouched))
    setChangedSquads(new Set(query.data.changed_squads))
    setChangedLeagues(new Set(query.data.changed_leagues))
  }, [query.data])

  const dirty = useMemo(() => JSON.stringify(draft) !== saved, [draft, saved])

  // live validation of the draft (debounced; the latest answer wins)
  useEffect(() => {
    if (!query.data) return
    if (!dirty) {
      // back to the saved project (restored, undone): its own results, and an answer still on the way no longer counts
      validateSeq.current++
      setIssues(query.data.issues)
      setDefaults(query.data.defaults)
      setUntouched(new Set(query.data.untouched))
      setChangedSquads(new Set(query.data.changed_squads))
      setChangedLeagues(new Set(query.data.changed_leagues))
      return
    }
    const seq = ++validateSeq.current
    const timer = setTimeout(() => {
      api
        .validate(draft)
        .then((r) => {
          if (seq !== validateSeq.current) return
          setIssues(r.issues)
          setDefaults(r.defaults)
          setUntouched(new Set(r.untouched))
          setChangedSquads(new Set(r.changed_squads))
      setChangedLeagues(new Set(r.changed_leagues))
          setChangedLeagues(new Set(r.changed_leagues))
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

  const setDraft = useCallback(
    (update: (p: Project) => Project) => setState((s) => splitOpened(update(withOpened(s.draft, s.opened)), s.opened)),
    [],
  )

  const save = useCallback(async () => {
    setSaving(true)
    try {
      const r = await api.saveProject(draft)
      // saving deletes the images the project does not use, the opened originals' too: their pages load them again
      bumpProjectImagesRevision() // uploads now have the fixed names of the images they replaced
      setSaved(JSON.stringify(r.project))
      setState({ draft: r.project, opened: NONE })
      setIssues(r.issues)
      setDefaults(r.defaults)
      setUntouched(new Set(r.untouched))
      setChangedSquads(new Set(r.changed_squads))
      setChangedLeagues(new Set(r.changed_leagues))
      queryClient.setQueryData(['project'], {
        project: r.project,
        issues: r.issues,
        defaults: r.defaults,
        untouched: r.untouched,
        changed_squads: r.changed_squads,
        changed_leagues: r.changed_leagues,
      })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
    } finally {
      setSaving(false)
    }
  }, [draft, queryClient])

  const value = useMemo<ProjectContextValue>(
    () => ({
      loaded: !!query.data,
      draft: view,
      dirty,
      issues,
      defaults,
      untouched,
      changedSquads,
      changedLeagues,
      opened: openedUids,
      saving,
      setDraft,
      updateLeague: (uid, patch) => setDraft((p) => ({ ...p, leagues: replace(p.leagues, uid, patch) })),
      updateTeam: (uid, patch) => setDraft((p) => ({ ...p, teams: replace(p.teams, uid, patch) })),
      updatePlayer: (uid, patch) => setDraft((p) => ({ ...p, players: replace(p.players, uid, patch) })),
      updateBoot: (uid, patch) => setDraft((p) => ({ ...p, boots: replace(p.boots ?? [], uid, patch) })),
      addLeague: (league) => setDraft((p) => ({ ...p, leagues: [...p.leagues, league] })),
      addTeam: (team) => setDraft((p) => ({ ...p, teams: [...p.teams, team] })),
      addPlayer: (player) => setDraft((p) => ({ ...p, players: [...p.players, player] })),
      addBoots: (boots) => setDraft((p) => ({ ...p, boots: [...(p.boots ?? []), ...boots] })),
      // once per original: a second load of the same one (two pages asking at once) is ignored
      openOriginal: (entry) =>
        setState((s) => {
          const view = withOpened(s.draft, s.opened)
          if ('league' in entry)
            return view.leagues.some((l) => l.original_id === entry.league.original_id)
              ? s
              : { ...s, opened: { ...s.opened, leagues: [...s.opened.leagues, entry.league] } }
          if ('team' in entry)
            return view.teams.some((t) => t.original_id === entry.team.original_id)
              ? s
              : { ...s, opened: { ...s.opened, teams: [...s.opened.teams, entry.team] } }
          if ('boot' in entry)
            return (view.boots ?? []).some((b) => b.original_id === entry.boot.original_id)
              ? s
              : { ...s, opened: { ...s.opened, boots: [...s.opened.boots, entry.boot] } }
          return view.players.some((p) => p.original_id === entry.player.original_id)
            ? s
            : { ...s, opened: { ...s.opened, players: [...s.opened.players, entry.player] } }
        }),
      removeLeague: (uid) => setDraft((p) => ({ ...p, leagues: p.leagues.filter((l) => l.uid !== uid) })),
      // removing a new team takes it out of its players' teams (they are not deleted); restoring an edited original
      // team (squad = the game's, GET /api/originals/teams/{id}/squad) also puts its squad back: who left returns
      // with the game's number and position (keeping his other teams), who joined leaves
      removeTeam: (uid, squad) =>
        setDraft((p) => {
          const team = p.teams.find((t) => t.uid === uid)
          const teamid = team?.original_id
          const ofGame = new Map((squad ?? []).map((l) => [l.player, l]))
          const restored = (pl: Player): Player => {
            const link = pl.original_id != null ? ofGame.get(pl.original_id) : undefined
            if (!link) return linkOf(pl, teamid!) ? { ...pl, teams: teamsWithout(pl, teamid!) } : pl
            const back = { team: teamid!, number: link.number, position: link.position }
            return { ...pl, teams: linkOf(pl, teamid!) ? pl.teams.map((l) => (l.team === teamid ? back : l)) : [...pl.teams, back] }
          }
          return {
            ...p,
            teams: p.teams.filter((t) => t.uid !== uid),
            players: p.players.map((pl) =>
              teamid != null ? (squad ? restored(pl) : pl) : linkOf(pl, uid) ? { ...pl, teams: teamsWithout(pl, uid) } : pl,
            ),
          }
        }),
      // deleting a new player also takes him out of captaincies, set pieces, lineups and the World Tour; removing an original
      // player's entry ("restore original") leaves him as the game has him (those places name him by playerid)
      removePlayer: (uid) =>
        setDraft((p) => ({
          ...p,
          players: p.players.filter((pl) => pl.uid !== uid),
          world_tour: p.world_tour && {
            dark: p.world_tour.dark?.filter((s) => s.player !== uid),
            white: p.world_tour.white?.filter((s) => s.player !== uid),
          },
          teams: p.players.find((pl) => pl.uid === uid)?.original_id != null ? p.teams : p.teams.map((t) => ({
            ...t,
            captain: t.captain === uid ? undefined : t.captain,
            takers: takersWithout(t, uid),
            lineups: lineupsWithout(t, uid),
          })),
        })),
      removeBoots: (uids) =>
        setDraft((p) => {
          const gone = new Set(uids)
          return { ...takeOff(p, gone), boots: (p.boots ?? []).filter((b) => !gone.has(b.uid)) }
        }),
      takeOffBoot: (uid, players) => setDraft((p) => takeOff(p, new Set([uid]), players && new Set(players))),
      save,
      discard: () => {
        setDraftState(JSON.parse(saved))
        if (query.data) {
          setIssues(query.data.issues)
          setDefaults(query.data.defaults)
          setUntouched(new Set(query.data.untouched))
          setChangedSquads(new Set(query.data.changed_squads))
          setChangedLeagues(new Set(query.data.changed_leagues))
    setChangedLeagues(new Set(query.data.changed_leagues))
        }
      },
    }),
    [query.data, view, dirty, issues, defaults, untouched, changedSquads, changedLeagues, openedUids, saving, setDraft, setDraftState, save, saved],
  )

  if (query.error) {
    return <LoadError page error={query.error} title={t('app.loadFailed')} onRetry={() => void query.refetch()} />
  }
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject must be used inside ProjectProvider')
  return ctx
}

/** Whether an original entry (entry = its uid) differs from the game, or a game team's squad (team = its teamid)
 * or a game league's teams (league = its leagueid) do. */
export function useWasEdited(entry?: string, team?: number | null, league?: number | null) {
  const { untouched, opened, changedSquads, changedLeagues } = useProject()
  return (
    (entry !== undefined && !opened.has(entry) && !untouched.has(entry)) ||
    (team != null && changedSquads.has(team)) ||
    (league != null && changedLeagues.has(league))
  )
}

/** Whether a project entry is one of the game's teams/players exactly as the game has it (only opened, or changed back):
 * lists show the game's row for it, not a project row. */
export function useSameAsGame() {
  const { untouched, opened } = useProject()
  return (uid: string) => opened.has(uid) || untouched.has(uid)
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
