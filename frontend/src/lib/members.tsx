import { useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { toast } from '@/lib/notify'
import { ApiError, api } from '@/api/client'
import type { League, LeagueKey, OriginalPlayer, Player, PlayerDefaults, PlayerRef, Project, Team, TeamKey, TeamLink } from '@/api/types'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'
import { GOALKEEPER } from '@/lib/teams'
import { firstFreeNumber, keyOfPath, linkedLeague, linkedTeam, linkOf, playerName, playerOf, playerRef, rosterOf, takePlace, teamKey, teamsWith } from '@/lib/players'
import { newUid, useProject } from '@/state/project'
import { useCatalog, useLookups, useOriginalPlayers } from '@/state/queries'

const ALL_GAME_PLAYERS = { limit: 5000 } // the whole list once (same query as the Players page)
const SQUAD_LIMIT = 100
const squadParams = (team: number) => ({ team, limit: SQUAD_LIMIT }) // same key as useOriginalPlayers

/** The game's players by playerid (the whole list, cached). */
export function useGamePlayers() {
  const items = useOriginalPlayers(ALL_GAME_PLAYERS).data?.items
  return useMemo(() => new Map((items ?? []).map((p) => [p.id, p])), [items])
}

/** Name of a team a link points to: a new team of the project, or one of the game's (its edited name when edited). */
export function useTeamName() {
  const { t } = useI18n()
  const { draft } = useProject()
  const { originalTeam } = useLookups()
  return (team: TeamKey) =>
    typeof team === 'string'
      ? draft.teams.find((tm) => tm.uid === team)?.name || t('team.unnamed')
      : draft.teams.find((tm) => tm.original_id === team)?.name || originalTeam.get(team)?.name || String(team)
}

/** A player of a team as the roster, captain, lineup and kit preview see it. kind: a new player of the project, one
 * of the game's players edited in the project, or one of the game's players as the game has him. */
export interface Member {
  ref: PlayerRef
  kind: 'project' | 'edited' | 'squad'
  name: string
  number?: number | null
  position?: number | null
  avatar: ReactNode
  player?: Player // project entry (new or edited)
  hidden?: boolean // out of the patch in this team (hidden here or out of the patch altogether): listed, takes no place
  outOfPatch?: boolean // the player is out of the patch altogether (Player.hidden), over being hidden in the team
}

/** Players of a team (pure): for one of the game's teams its own players (`squad`, as the game has them; an edited one
 * shows his entry, and only while he stays), then the project's players who joined it. */
export function membersOf(
  project: Project,
  team: TeamKey,
  squad: OriginalPlayer[],
  defaults: Record<string, PlayerDefaults>,
  unnamed: string,
): Member[] {
  const edited = new Map(project.players.filter((p) => p.original_id != null).map((p) => [p.original_id!, p]))
  const fromEntry = (p: Player, game?: OriginalPlayer): Member => {
    const link = linkOf(p, team)
    const inherited = defaults[p.uid]?.team === team ? defaults[p.uid] : undefined
    const own = game && typeof team === 'number' ? game : undefined
    return {
      ref: playerRef(p),
      kind: p.original_id != null ? 'edited' : 'project',
      name: playerName(p, unnamed),
      number: link?.number ?? inherited?.number ?? own?.number,
      position: link?.position ?? inherited?.position ?? own?.position,
      avatar: <PlayerAvatar player={p} />,
      player: p,
      hidden: !!(p.hidden || link?.hidden),
      outOfPatch: !!p.hidden,
    }
  }
  const out: Member[] = []
  const listed = new Set<PlayerRef>()
  for (const g of squad) {
    const entry = edited.get(g.id)
    if (entry && !linkOf(entry, team)) continue // left the team
    out.push(
      entry
        ? fromEntry(entry, g)
        : { ref: g.id, kind: 'squad', name: g.display_name, number: g.number, position: g.position, avatar: <OriginalPlayerAvatar player={g} /> },
    )
    listed.add(g.id)
  }
  for (const p of rosterOf(project, team)) if (!listed.has(playerRef(p))) out.push(fromEntry(p))
  return out
}

/** Members of any team (new team uid or the game's teamid); hidden project players included. */
export function useSquad(team: TeamKey): Member[] {
  const { t } = useI18n()
  const { draft, defaults } = useProject()
  const game = typeof team === 'number'
  const squad = useOriginalPlayers(squadParams(game ? team : 0), game).data?.items
  return membersOf(draft, team, game ? (squad ?? []) : [], defaults, t('common.unnamed'))
}

export const useTeamMembers = (team: Team) => useSquad(teamKey(team))

/** The project entry of one of the game's players, created (loaded from the game) the first time. */
export function useGamePlayerEntry() {
  const { t } = useI18n()
  const { draft, openOriginal } = useProject()
  return async (playerid: number): Promise<Player | null> => {
    const known = playerOf(draft, playerid)
    if (known) return known
    try {
      const entry = await api.editOriginalPlayer(playerid, newUid())
      openOriginal({ player: entry })
      return entry
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('players.editOriginalFailed'))
      return null
    }
  }
}

/** The project entry of one of the game's teams, created (loaded from the game) the first time. */
export function useGameTeamEntry() {
  const { t } = useI18n()
  const { draft, openOriginal } = useProject()
  return async (teamid: number): Promise<Team | null> => {
    const known = linkedTeam(draft, teamid)
    if (known) return known
    try {
      const entry = await api.editOriginalTeam(teamid, newUid())
      openOriginal({ team: entry })
      return entry
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('teams.editOriginalFailed'))
      return null
    }
  }
}

/** The project entry of one of the game's leagues, created (loaded from the game) the first time. */
export function useGameLeagueEntry() {
  const { t } = useI18n()
  const { draft, openOriginal } = useProject()
  return async (leagueid: number): Promise<League | null> => {
    const known = linkedLeague(draft, leagueid)
    if (known) return known
    try {
      const entry = await api.editOriginalLeague(leagueid, newUid())
      openOriginal({ league: entry })
      return entry
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('leagues.editOriginalFailed'))
      return null
    }
  }
}

type EntryKind = 'league' | 'team' | 'player'

/** The league/team/player an edit page address names (leaguePath/teamPath/playerPath): a new one by uid, one of the
 * game's by its id, loaded from the game when the project does not have it yet (also after a reload, or a save that
 * dropped it; `load` false: never, e.g. a league the game does not let edit). An old address of an original by uid
 * moves to its game id. loading: still coming from the game. */
export function useEntryOfPath<T extends League | Team | Player>(kind: EntryKind, param: string | undefined, load = true) {
  const { loaded, draft } = useProject()
  const ensure = { league: useGameLeagueEntry(), team: useGameTeamEntry(), player: useGamePlayerEntry() }[kind]
  const navigate = useNavigate()
  const location = useLocation()
  const [failed, setFailed] = useState<number>()
  const key = keyOfPath(param)
  const entry = (key === undefined
    ? undefined
    : kind === 'league'
      ? linkedLeague(draft, key)
      : kind === 'team'
        ? linkedTeam(draft, key)
        : playerOf(draft, key)) as T | undefined
  const gameId = typeof key === 'number' ? key : undefined
  const legacy = typeof key === 'string' ? entry?.original_id : undefined
  useEffect(() => {
    if (legacy != null) navigate(`/${kind}s/${legacy}${location.search}`, { replace: true, state: location.state })
  }, [legacy, kind, navigate, location.search, location.state])
  const absent = load && loaded && gameId !== undefined && !entry
  useEffect(() => {
    if (!absent || gameId === undefined) return
    let live = true
    void ensure(gameId).then((e) => {
      if (live && !e) setFailed(gameId)
    })
    return () => {
      live = false
    }
    // once per absent id (the ensure functions are new on each render)
  }, [absent, gameId, kind])
  return { entry, loading: !entry && (!loaded || (absent && failed !== gameId)) }
}

/** A team (new team uid or the game's teamid) joining a league or leaving one; its other leagues stay (a team plays
 * in several leagues, validated in game). One of the game's teams gets its entry first (applied by teamid). */
export function useTeamLeagues() {
  const { setDraft } = useProject()
  const ensure = useGameTeamEntry()
  const change = async (team: TeamKey, update: (leagues: LeagueKey[]) => LeagueKey[]) => {
    if (typeof team === 'number' && !(await ensure(team))) return false
    setDraft((p) => ({ ...p, teams: p.teams.map((t) => (teamKey(t) === team ? { ...t, leagues: update(t.leagues) } : t)) }))
    return true
  }
  return {
    join: (team: TeamKey, league: LeagueKey) => change(team, (ls) => (ls.includes(league) ? ls : [...ls, league])),
    leave: (team: TeamKey, league: LeagueKey) => change(team, (ls) => ls.filter((l) => l !== league)),
  }
}

const withLink = (project: Project, ref: PlayerRef, team: TeamKey, link: Omit<TeamLink, 'team'>): Project => {
  const player = playerOf(project, ref)
  return {
    ...project,
    players: project.players.map((p) => (p === player ? { ...p, teams: [...p.teams, { team, ...link }] } : p)),
  }
}

/** The project with a player shown or hidden in one team (TeamLink.hidden): hidden, he stays in its roster but out
 * of the patch there (the game's players need an entry first, see useGamePlayerEntry). */
export const hideInTeam = (project: Project, ref: PlayerRef, team: TeamKey, hidden: boolean): Project => {
  const player = playerOf(project, ref)
  return { ...project, players: project.players.map((p) => (p === player ? { ...p, teams: teamsWith(p, team, { hidden }) } : p)) }
}

/** Fetches the game's squad of a team (new team: none), cached like useSquad. */
function useFetchSquad() {
  const queryClient = useQueryClient()
  return async (team: TeamKey) =>
    typeof team === 'number'
      ? (
          await queryClient.fetchQuery({
            queryKey: ['originals', 'players', squadParams(team)],
            queryFn: () => api.originalPlayers(squadParams(team)),
            staleTime: Infinity,
          })
        ).items
      : []
}

interface PendingJoin {
  ref: PlayerRef
  name: string
  team: TeamKey
  candidates: Member[]
  numbers: (number | null | undefined)[]
}

/** Putting a player into a team: a team may have any number of players, at most max_roster of them in the patch.
 * When the team already has that many in the patch a dialog asks who is left out of the patch in it for him (that
 * one stays in the team, hidden there; the joining player takes his number, position, captaincy, set pieces and
 * lineup place), or he joins hidden himself. join(ref, team): ref = Player.ref (a game player not in the project yet
 * gets an entry first). */
export function useJoinTeam() {
  const { t } = useI18n()
  const { draft, setDraft, defaults } = useProject()
  const catalog = useCatalog().data
  const ensure = useGamePlayerEntry()
  const fetchSquad = useFetchSquad()
  const teamName = useTeamName()
  const max = catalog?.max_roster ?? 13
  const [pending, setPending] = useState<PendingJoin | null>(null)
  const [hiding, setHiding] = useState<string>()

  const join = async (ref: PlayerRef, team: TeamKey) => {
    if (typeof ref === 'number' && !(await ensure(ref))) return
    const all = membersOf(draft, team, await fetchSquad(team), defaults, t('common.unnamed'))
    const members = all.filter((m) => !m.hidden)
    // a new team gets a free number; one of the game's: the build gives a free one
    const number = typeof team === 'string' ? firstFreeNumber(all.map((m) => m.number)) : undefined
    if (members.length < max) {
      setDraft((p) => withLink(p, ref, team, { number }))
      return
    }
    const joiner = playerOf(draft, ref)
    setHiding(undefined)
    setPending({
      ref,
      team,
      candidates: members,
      numbers: all.map((m) => m.number),
      name: joiner ? playerName(joiner, t('common.unnamed')) : String(ref),
    })
  }

  const confirm = async () => {
    if (!pending) return
    const { ref, team } = pending
    const out = pending.candidates.find((m) => String(m.ref) === hiding)
    if (!out) {
      const number = typeof team === 'string' ? firstFreeNumber(pending.numbers) : undefined
      setDraft((p) => withLink(p, ref, team, { number, hidden: true }))
      setPending(null)
      return
    }
    if (out.kind === 'squad' && !(await ensure(out.ref as number))) return
    setDraft((p) =>
      withLink(hideInTeam(takePlace(p, team, out.ref, ref), out.ref, team, true), ref, team, { number: out.number, position: out.position }),
    )
    setPending(null)
  }

  const dialog = (
    <Dialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('join.title', { team: pending ? teamName(pending.team) : '', max })}</DialogTitle>
          <DialogDescription>{t('join.description', { max, name: pending?.name ?? '' })}</DialogDescription>
        </DialogHeader>
        <Select value={hiding ?? ''} onValueChange={setHiding}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('join.pick')} />
          </SelectTrigger>
          <SelectContent>
            {pending?.candidates.map((m) => (
              <SelectItem key={String(m.ref)} value={String(m.ref)}>
                {m.name}
                {m.number != null && ` · ${m.number}`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button variant="outline" onClick={() => setPending(null)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void confirm()}>{hiding ? t('join.confirm') : t('join.confirmHidden')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
  return { join, dialog }
}

/** Players that came in a shared zip fitted to the patch limit of their teams (no dialog): in each team they joined,
 * the ones already in the project keep how they were; the newcomers fill the places left up to max (a goalkeeper
 * first when the team has none in the patch, then by overall) and the others join hidden in that team. squads: the
 * game's squad of each game team they joined. */
export function fitImportedRosters(
  before: Project,
  after: Project,
  imported: string[],
  squads: Map<number, OriginalPlayer[]>,
  max: number,
): Project {
  const oldLink = (p: Player, team: TeamKey) => {
    const old = before.players.find((b) => b.uid === p.uid || (p.original_id != null && b.original_id === p.original_id))
    return old && linkOf(old, team)
  }
  const players = new Map(after.players.map((p) => [p.uid, p]))
  const newcomers = new Map<TeamKey, Player[]>()
  for (const uid of imported) {
    const p = players.get(uid)
    if (!p) continue
    for (const lk of p.teams) {
      const old = oldLink(p, lk.team)
      if (old) {
        const cur = players.get(uid)!
        players.set(uid, { ...cur, teams: teamsWith(cur, lk.team, { hidden: old.hidden }) }) // as it was
      } else if (!p.hidden && !lk.hidden) newcomers.set(lk.team, [...(newcomers.get(lk.team) ?? []), p])
    }
  }
  let project: Project = { ...after, players: [...players.values()] }
  for (const [team, incoming] of newcomers) {
    const coming = new Set(incoming.map((p) => p.uid))
    const shown = membersOf(project, team, typeof team === 'number' ? (squads.get(team) ?? []) : [], {}, '').filter(
      (m) => !m.hidden && !(m.player && coming.has(m.player.uid)),
    )
    let places = max - shown.length
    const byOverall = [...incoming].sort((a, b) => (b.skills?.overall ?? 0) - (a.skills?.overall ?? 0))
    const keeper = shown.some((m) => m.position === GOALKEEPER)
      ? undefined
      : byOverall.find((p) => linkOf(p, team)?.position === GOALKEEPER)
    const order = keeper ? [keeper, ...byOverall.filter((p) => p !== keeper)] : byOverall
    const left = new Set<string>()
    for (const p of order) if (places-- <= 0) left.add(p.uid)
    project = {
      ...project,
      players: project.players.map((p) => (left.has(p.uid) ? { ...p, teams: teamsWith(p, team, { hidden: true }) } : p)),
    }
  }
  return project
}

/** fitImportedRosters with the game's squads of the teams the imported players joined fetched first. */
export function useFitImported() {
  const catalog = useCatalog().data
  const fetchSquad = useFetchSquad()
  return async (players: Player[]) => {
    const games = [...new Set(players.flatMap((p) => p.teams.map((l) => l.team)))].filter((k): k is number => typeof k === 'number')
    const squads = new Map(await Promise.all(games.map(async (g) => [g, await fetchSquad(g)] as const)))
    const max = catalog?.max_roster ?? 13
    return (before: Project, after: Project) => fitImportedRosters(before, after, players.map((p) => p.uid), squads, max)
  }
}
