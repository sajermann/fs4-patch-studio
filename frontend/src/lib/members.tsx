import { useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { OriginalPlayer, Player, PlayerDefaults, PlayerRef, Project, Team, TeamKey, TeamLink } from '@/api/types'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'
import { firstFreeNumber, keyOfPath, leaveTeam, linkedTeam, linkOf, playerName, playerOf, playerRef, rosterOf, takePlace, teamKey } from '@/lib/players'
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
  hidden?: boolean // project player out of the patch: listed, but takes no place
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
      hidden: p.hidden,
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

/** The team/player an edit page address names (teamPath/playerPath): a new one by uid, one of the game's by its id,
 * loaded from the game when the project does not have it yet (also after a reload, or a save that dropped it). An old
 * address of an original by uid moves to its game id. loading: still coming from the game. */
export function useEntryOfPath<T extends Team | Player>(kind: 'team' | 'player', param: string | undefined) {
  const { loaded, draft } = useProject()
  const ensureTeam = useGameTeamEntry()
  const ensurePlayer = useGamePlayerEntry()
  const navigate = useNavigate()
  const location = useLocation()
  const [failed, setFailed] = useState<number>()
  const key = keyOfPath(param)
  const entry = (key === undefined ? undefined : kind === 'team' ? linkedTeam(draft, key) : playerOf(draft, key)) as T | undefined
  const gameId = typeof key === 'number' ? key : undefined
  const legacy = typeof key === 'string' ? entry?.original_id : undefined
  useEffect(() => {
    if (legacy != null) navigate(`/${kind}s/${legacy}${location.search}`, { replace: true, state: location.state })
  }, [legacy, kind, navigate, location.search, location.state])
  const absent = loaded && gameId !== undefined && !entry
  useEffect(() => {
    if (!absent || gameId === undefined) return
    let live = true
    void (kind === 'team' ? ensureTeam(gameId) : ensurePlayer(gameId)).then((e) => {
      if (live && !e) setFailed(gameId)
    })
    return () => {
      live = false
    }
    // once per absent id (the ensure functions are new on each render)
  }, [absent, gameId, kind])
  return { entry, loading: !entry && (!loaded || (absent && failed !== gameId)) }
}

const withLink = (project: Project, ref: PlayerRef, team: TeamKey, link: Omit<TeamLink, 'team'>): Project => {
  const player = playerOf(project, ref)
  return {
    ...project,
    players: project.players.map((p) => (p === player ? { ...p, teams: [...p.teams, { team, ...link }] } : p)),
  }
}

/** Putting a player into a team. When the team is full a dialog asks who leaves it: he leaves that team only (a free
 * agent when it was his only one) and the joining player takes his number, position, captaincy, set pieces and
 * lineup place. join(ref, team): ref = Player.ref (a game player not in the project yet gets an entry first). */
export function useJoinTeam() {
  const { t } = useI18n()
  const { draft, setDraft, defaults } = useProject()
  const catalog = useCatalog().data
  const queryClient = useQueryClient()
  const ensure = useGamePlayerEntry()
  const teamName = useTeamName()
  const max = catalog?.max_roster ?? 13
  const [pending, setPending] = useState<{ ref: PlayerRef; name: string; team: TeamKey; candidates: Member[] } | null>(null)
  const [leaving, setLeaving] = useState<string>()

  const join = async (ref: PlayerRef, team: TeamKey) => {
    if (typeof ref === 'number' && !(await ensure(ref))) return
    const squad =
      typeof team === 'number'
        ? (await queryClient.fetchQuery({
            queryKey: ['originals', 'players', squadParams(team)],
            queryFn: () => api.originalPlayers(squadParams(team)),
            staleTime: Infinity,
          })).items
        : []
    const members = membersOf(draft, team, squad, defaults, t('common.unnamed')).filter((m) => !m.hidden)
    if (members.length < max) {
      // a new team gets a free number; one of the game's: the build gives a free one
      const number = typeof team === 'string' ? firstFreeNumber(members.map((m) => m.number)) : undefined
      setDraft((p) => withLink(p, ref, team, { number }))
      return
    }
    const joiner = playerOf(draft, ref)
    setLeaving(undefined)
    setPending({ ref, team, candidates: members, name: joiner ? playerName(joiner, t('common.unnamed')) : String(ref) })
  }

  const confirm = async () => {
    const left = pending?.candidates.find((m) => String(m.ref) === leaving)
    if (!pending || !left) return
    if (left.kind === 'squad' && !(await ensure(left.ref as number))) return
    const { ref, team } = pending
    setDraft((p) =>
      withLink(leaveTeam(takePlace(p, team, left.ref, ref), left.ref, team), ref, team, { number: left.number, position: left.position }),
    )
    setPending(null)
  }

  const dialog = (
    <Dialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('join.title', { team: pending ? teamName(pending.team) : '' })}</DialogTitle>
          <DialogDescription>{t('join.description', { max, name: pending?.name ?? '' })}</DialogDescription>
        </DialogHeader>
        <Select value={leaving ?? ''} onValueChange={setLeaving}>
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
          <Button disabled={!leaving} onClick={() => void confirm()}>
            {t('join.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
  return { join, dialog }
}
