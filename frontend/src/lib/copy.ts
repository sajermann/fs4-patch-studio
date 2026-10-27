import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import type { Player, Project } from '@/api/types'
import { translate, useI18n } from '@/i18n'
import { useLeagueTeams } from '@/lib/teams'
import { copyLineups } from '@/lib/lineup'
import { newUid, useProject } from '@/state/project'
import { useCatalog } from '@/state/queries'

/** Copy of a player with a new uid and no game id (the build gives a new one); a real face gets its files copied. */
async function clonePlayer(player: Player, patch: Partial<Player>): Promise<Player> {
  const uid = newUid('jg')
  const copy: Player = { ...player, ...patch, uid, player_id: undefined }
  if (!player.generic && player.face) {
    try {
      await api.copyFace(player.uid, uid, player.face.source_id)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : translate('copy.faceFailed'))
      copy.generic = true
      copy.face = undefined
    }
  }
  return copy
}

const firstFreeNumber = (players: Player[]) => {
  const used = new Set(players.map((p) => p.number))
  return Array.from({ length: 99 }, (_, i) => i + 1).find((n) => !used.has(n))
}

/** "Copy" of leagues, teams and players: duplicates in the draft (new uids, game ids left to the build) and returns
 * the new uid, or null when the copy is not possible (limits). */
export function useCopy() {
  const { t } = useI18n()
  const { draft, setDraft } = useProject()
  const catalog = useCatalog().data
  const suffix = ` ${t('copy.suffix')}`
  const leagueTeams = useLeagueTeams()
  const maxLeagues = catalog?.max_leagues ?? 39
  const maxRoster = catalog?.max_roster ?? 13
  const activeRoster = (project: Project, team: string) => project.players.filter((p) => p.team === team && !p.hidden)

  const canCopyLeague = draft.leagues.filter((l) => !l.hidden).length < maxLeagues
  const copyLeague = (uid: string) => {
    const league = draft.leagues.find((l) => l.uid === uid)
    if (!league || !canCopyLeague) return null
    const copy = { ...league, uid: newUid('lg'), name: league.name + suffix, league_id: undefined }
    setDraft((p) => ({ ...p, leagues: [...p.leagues, copy] }))
    return copy.uid
  }

  // the copy goes to the same league: it must have room for one more team
  const canCopyTeam = (uid: string) => {
    const team = draft.teams.find((t) => t.uid === uid)
    return !!team && !leagueTeams.isFull(team.league)
  }
  const copyTeam = async (uid: string, withRoster: boolean) => {
    const team = draft.teams.find((t) => t.uid === uid)
    if (!team || !canCopyTeam(uid)) return null
    const teamUid = newUid('tm')
    const roster = withRoster ? draft.players.filter((p) => p.team === uid) : []
    const players = await Promise.all(roster.map((p) => clonePlayer(p, { team: teamUid })))
    const captain = team.captain && roster.findIndex((p) => p.uid === team.captain)
    const copy = {
      ...team,
      uid: teamUid,
      name: team.name + suffix,
      team_id: undefined,
      captain: typeof captain === 'number' && captain >= 0 ? players[captain].uid : undefined,
      lineups: copyLineups(team, new Map(roster.map((p, k) => [p.uid, players[k].uid]))),
    }
    setDraft((p) => ({ ...p, teams: [...p.teams, copy], players: [...p.players, ...players] }))
    return teamUid
  }

  // same team when its roster has room (with a free shirt number), else a free agent
  const copyPlayer = async (uid: string) => {
    const player = draft.players.find((p) => p.uid === uid)
    if (!player) return null
    const team = player.team && activeRoster(draft, player.team).length < maxRoster ? player.team : null
    if (player.team && !team) toast.info(t('copy.rosterFull', { max: maxRoster }))
    const copy = await clonePlayer(player, {
      team,
      // numbers of hidden players too: they may come back
      number: team ? firstFreeNumber(draft.players.filter((p) => p.team === team)) : player.number,
    })
    setDraft((p) => ({ ...p, players: [...p.players, copy] }))
    return copy.uid
  }

  return { canCopyLeague, maxLeagues, copyLeague, canCopyTeam, copyTeam, copyPlayer, maxLeagueTeams: leagueTeams.max }
}
