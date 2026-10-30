import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import type { Player, Project } from '@/api/types'
import { translate, useI18n } from '@/i18n'
import { useLeagueTeams } from '@/lib/teams'
import { copyLineups } from '@/lib/lineup'
import { firstFreeNumber, linkOf, numbersIn, rosterOf } from '@/lib/players'
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
  const activeRoster = (project: Project, team: string) => rosterOf(project, team).filter((p) => !p.hidden)

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
    // the copies only play for the copied team (their other teams already have the originals); the game's players
    // are not copied (they would be new players with the same face and name)
    const roster = withRoster ? rosterOf(draft, uid).filter((p) => p.original_id == null) : []
    const players = await Promise.all(roster.map((p) => clonePlayer(p, { teams: [{ ...linkOf(p, uid)!, team: teamUid }] })))
    const captain = team.captain && roster.findIndex((p) => p.uid === team.captain)
    const copy = {
      ...team,
      uid: teamUid,
      name: team.name + suffix,
      team_id: undefined,
      captain: typeof captain === 'number' && captain >= 0 ? players[captain].uid : undefined,
      takers: Object.fromEntries(
        Object.entries(team.takers ?? {}).flatMap(([role, p]) => {
          const k = roster.findIndex((pl) => pl.uid === p)
          return k >= 0 ? [[role, players[k].uid]] : []
        }),
      ),
      lineups: copyLineups(team, new Map(roster.map((p, k) => [p.uid, players[k].uid]))),
    }
    setDraft((p) => ({ ...p, teams: [...p.teams, copy], players: [...p.players, ...players] }))
    return teamUid
  }

  // same new teams whose roster has room (with a free shirt number); the game's teams are left out (a place there
  // means replacing one of their players)
  const copyPlayer = async (uid: string) => {
    const player = draft.players.find((p) => p.uid === uid)
    if (!player) return null
    const teams = player.teams.filter(
      (l) => typeof l.team === 'string' && activeRoster(draft, l.team).length < maxRoster,
    )
    if (teams.length < player.teams.length) toast.info(t('copy.rosterFull', { max: maxRoster }))
    const copy = await clonePlayer(player, {
      // numbers of hidden players too: they may come back
      teams: teams.map((l) => ({ ...l, number: firstFreeNumber(numbersIn(draft, l.team)) })),
    })
    setDraft((p) => ({ ...p, players: [...p.players, copy] }))
    return copy.uid
  }

  return { canCopyLeague, maxLeagues, copyLeague, canCopyTeam, copyTeam, copyPlayer, maxLeagueTeams: leagueTeams.max }
}
