import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { ApiError, api, bumpProjectImagesRevision } from '@/api/client'
import { LoadError } from '@/components/layout/LoadError'
import { useI18n } from '@/i18n'
import { withFittedBody } from '@/lib/body'
import { lineupsWithout, takersWithout } from '@/lib/lineup'
import { linkOf, teamsWithout } from '@/lib/players'
import type { Ball, Boot, Glove, Issue, League, OriginalSquadLink, Player, PlayerDefaults, Project, Team } from '@/api/types'

const EMPTY: Project = { version: 9, leagues: [], teams: [], players: [], boots: [], gloves: [], balls: [] }
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
  /** uids of the entries saved in the project (an entry not in it is still being created) */
  savedUids: Set<string>
  saving: boolean
  setDraft: (update: (p: Project) => Project) => void
  updateLeague: (uid: string, patch: Partial<League>) => void
  updateTeam: (uid: string, patch: Partial<Team>) => void
  updatePlayer: (uid: string, patch: Partial<Player>) => void
  updateBoot: (uid: string, patch: Partial<Boot>) => void
  updateGlove: (uid: string, patch: Partial<Glove>) => void
  updateBall: (uid: string, patch: Partial<Ball>) => void
  addLeague: (league: League) => void
  addTeam: (team: Team) => void
  addPlayer: (player: Player) => void
  addBoots: (boots: Boot[]) => void
  addGloves: (gloves: Glove[]) => void
  addBalls: (balls: Ball[]) => void
  /** an original league/team/player/boot/glove/ball loaded from the game, shown as it is until something changes
   * (see `opened`) */
  openOriginal: (
    entry: { league: League } | { team: Team } | { player: Player } | { boot: Boot } | { glove: Glove } | { ball: Ball },
  ) => void
  removeLeague: (uid: string) => void
  removeTeam: (uid: string, squad?: OriginalSquadLink[]) => void
  removePlayer: (uid: string) => void
  /** deleting new boots also takes them off the players wearing them; an edited game boot goes back to the game's */
  removeBoots: (uids: string[]) => void
  /** takes a new boot off players (all of them by default): each one is back to the game boot he had on those
   * surfaces, or his default */
  takeOffBoot: (uid: string, players?: string[]) => void
  /** deleting new gloves also takes them off the goalkeepers wearing them; an edited game glove goes back to the
   * game's */
  removeGloves: (uids: string[]) => void
  /** takes a glove (a new glove's uid or a game glove's code) off players (all of them by default): each one is back
   * to "not picked" (his code stays as it was) */
  takeOffGlove: (ref: string | number, players?: string[]) => void
  /** deleting new balls also takes them off the stadiums using them (back to the game's ball); an edited game ball
   * goes back to the game's files */
  removeBalls: (uids: string[]) => void
  /** sets the ball of stadium rows (stadiumids): a new ball's uid or a game ball's id; null = the game's own (each
   * row's `original` ball: kept only when it differs) */
  setStadiumBalls: (rows: { id: number; original: number }[], ball: string | number | null) => void
  save: () => Promise<void>
  /** saves once the draft has the change just made (the next render): for changes made right before leaving the page */
  requestSave: () => void
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
  gloves: Glove[]
  balls: Ball[]
}
/** The project with the gloves `gone` (uids or game codes) taken off its players (only `players`, when given). */
const takeOffGloves = (p: Project, gone: Set<string | number>, players?: Set<string>): Project => ({
  ...p,
  players: p.players.map((pl) =>
    (!players || players.has(pl.uid)) && pl.glove != null && gone.has(pl.glove) ? { ...pl, glove: undefined } : pl,
  ),
})

/** The project with the boots `gone` taken off its players (only `players`, when given). */
const takeOff = (p: Project, gone: Set<string>, players?: Set<string>): Project => ({
  ...p,
  players: p.players.map((pl) =>
    (!players || players.has(pl.uid)) && pl.boots && Object.values(pl.boots).some((u) => u && gone.has(u))
      ? { ...pl, boots: Object.fromEntries(Object.entries(pl.boots).filter(([, u]) => !u || !gone.has(u))) }
      : pl,
  ),
})

const NONE: Opened = { leagues: [], teams: [], players: [], boots: [], gloves: [], balls: [] }

/** The project with the stadium rows using the balls `gone` (new balls' uids) back on the game's ball. */
const offStadiums = (p: Project, gone: Set<string | number>): Project => {
  const picked = p.originals?.stadium_balls
  if (!picked || !Object.values(picked).some((b) => gone.has(b))) return p
  const kept = Object.fromEntries(Object.entries(picked).filter(([, b]) => !gone.has(b)))
  return { ...p, originals: { ...p.originals, stadium_balls: kept } }
}

const withOpened = (draft: Project, opened: Opened): Project =>
  opened.leagues.length || opened.teams.length || opened.players.length || opened.boots.length || opened.gloves.length || opened.balls.length
    ? {
        ...draft,
        leagues: [...draft.leagues, ...opened.leagues],
        teams: [...draft.teams, ...opened.teams],
        players: [...draft.players, ...opened.players],
        boots: [...(draft.boots ?? []), ...opened.boots],
        gloves: [...(draft.gloves ?? []), ...opened.gloves],
        balls: [...(draft.balls ?? []), ...opened.balls],
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
  const gloves = split(next.gloves ?? [], opened.gloves)
  const balls = split(next.balls ?? [], opened.balls)
  return {
    draft: {
      ...next,
      leagues: leagues.project,
      teams: teams.project,
      players: players.project,
      boots: boots.project,
      gloves: gloves.project,
      balls: balls.project,
    },
    opened: {
      leagues: leagues.opened,
      teams: teams.opened,
      players: players.opened,
      boots: boots.opened,
      gloves: gloves.opened,
      balls: balls.opened,
    },
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
      new Set(
        [
          ...state.opened.leagues,
          ...state.opened.teams,
          ...state.opened.players,
          ...state.opened.boots,
          ...state.opened.gloves,
          ...state.opened.balls,
        ].map((e) => e.uid),
      ),
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
  const savedUids = useMemo(() => {
    const p = JSON.parse(saved) as Project
    return new Set([p.leagues, p.teams, p.players, p.boots ?? [], p.gloves ?? [], p.balls ?? []].flatMap((l) => l.map((e) => e.uid)))
  }, [saved])

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

  // requestSave: the provider outlives the page that asked (it may open another address right after)
  const [saveRequested, setSaveRequested] = useState(false)
  useEffect(() => {
    if (!saveRequested) return
    setSaveRequested(false)
    save().catch((e) => toast.error(e instanceof ApiError ? e.message : t('common.saveFailed')))
  }, [saveRequested, save, t])

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
      savedUids,
      saving,
      setDraft,
      updateLeague: (uid, patch) => setDraft((p) => ({ ...p, leagues: replace(p.leagues, uid, patch) })),
      updateTeam: (uid, patch) => setDraft((p) => ({ ...p, teams: replace(p.teams, uid, patch) })),
      // a new height moves the player's body type to its height class (lib/body), from any screen that sets it
      updatePlayer: (uid, patch) =>
        setDraft((p) => ({ ...p, players: p.players.map((e) => (e.uid === uid ? { ...e, ...withFittedBody(e, patch) } : e)) })),
      updateBoot: (uid, patch) => setDraft((p) => ({ ...p, boots: replace(p.boots ?? [], uid, patch) })),
      updateGlove: (uid, patch) => setDraft((p) => ({ ...p, gloves: replace(p.gloves ?? [], uid, patch) })),
      updateBall: (uid, patch) => setDraft((p) => ({ ...p, balls: replace(p.balls ?? [], uid, patch) })),
      addLeague: (league) => setDraft((p) => ({ ...p, leagues: [...p.leagues, league] })),
      addTeam: (team) => setDraft((p) => ({ ...p, teams: [...p.teams, team] })),
      addPlayer: (player) => setDraft((p) => ({ ...p, players: [...p.players, player] })),
      addBoots: (boots) => setDraft((p) => ({ ...p, boots: [...(p.boots ?? []), ...boots] })),
      addGloves: (gloves) => setDraft((p) => ({ ...p, gloves: [...(p.gloves ?? []), ...gloves] })),
      addBalls: (balls) => setDraft((p) => ({ ...p, balls: [...(p.balls ?? []), ...balls] })),
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
          if ('ball' in entry)
            return (view.balls ?? []).some((b) => b.original_id === entry.ball.original_id)
              ? s
              : { ...s, opened: { ...s.opened, balls: [...s.opened.balls, entry.ball] } }
          if ('glove' in entry)
            return (view.gloves ?? []).some((g) => g.original_id === entry.glove.original_id)
              ? s
              : { ...s, opened: { ...s.opened, gloves: [...s.opened.gloves, entry.glove] } }
          if ('boot' in entry)
            return (view.boots ?? []).some((b) => b.original_id === entry.boot.original_id)
              ? s
              : { ...s, opened: { ...s.opened, boots: [...s.opened.boots, entry.boot] } }
          return view.players.some((p) => p.original_id === entry.player.original_id)
            ? s
            : { ...s, opened: { ...s.opened, players: [...s.opened.players, entry.player] } }
        }),
      // deleting a new league takes it off its teams first (a team left with no league stays out of the patch)
      removeLeague: (uid) =>
        setDraft((p) => ({
          ...p,
          leagues: p.leagues.filter((l) => l.uid !== uid),
          teams: p.teams.map((t) => (t.leagues.includes(uid) ? { ...t, leagues: t.leagues.filter((l) => l !== uid) } : t)),
        })),
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
      removeGloves: (uids) =>
        setDraft((p) => {
          const gone = new Set(uids)
          // only new gloves come off their players: an edited game glove stays picked by its code
          const news = new Set<string | number>((p.gloves ?? []).filter((g) => gone.has(g.uid) && g.original_id == null).map((g) => g.uid))
          return { ...takeOffGloves(p, news), gloves: (p.gloves ?? []).filter((g) => !gone.has(g.uid)) }
        }),
      takeOffGlove: (ref, players) => setDraft((p) => takeOffGloves(p, new Set([ref]), players && new Set(players))),
      removeBalls: (uids) =>
        setDraft((p) => {
          const gone = new Set(uids)
          // only new balls come off their stadiums: an edited game ball stays picked by its id
          const news = new Set<string | number>((p.balls ?? []).filter((b) => gone.has(b.uid) && b.original_id == null).map((b) => b.uid))
          return { ...offStadiums(p, news), balls: (p.balls ?? []).filter((b) => !gone.has(b.uid)) }
        }),
      setStadiumBalls: (rows, ball) =>
        setDraft((p) => {
          const next = { ...(p.originals?.stadium_balls ?? {}) }
          for (const row of rows) {
            if (ball == null || ball === row.original) delete next[row.id]
            else next[row.id] = ball
          }
          return { ...p, originals: { ...p.originals, stadium_balls: next } }
        }),
      save,
      requestSave: () => setSaveRequested(true),
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
    [query.data, view, dirty, issues, defaults, untouched, changedSquads, changedLeagues, openedUids, savedUids, saving, setDraft, setDraftState, save, saved],
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
