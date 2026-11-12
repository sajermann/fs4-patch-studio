import type { Project } from '@/api/types'
import type { TFunction } from '@/i18n'
import { leagueKey, leaguePath, playerPath, playerRef, teamKey, teamPath } from '@/lib/players'

/** Label and page of the league/team/player with this uid in the project ("Jogador: Gustavo Gómez"); null when the
 * project has no such entry (deleted since, or no uid). */
export function entityLink(t: TFunction, project: Project, uid: string | null | undefined) {
  if (!uid) return null
  const unnamed = t('common.unnamed')
  const league = project.leagues.find((l) => l.uid === uid)
  if (league) return { label: t('issues.linkLeague', { name: league.name || unnamed }), to: leaguePath(leagueKey(league)) }
  const team = project.teams.find((tm) => tm.uid === uid)
  if (team) return { label: t('issues.linkTeam', { name: team.name || unnamed }), to: teamPath(teamKey(team)) }
  const player = project.players.find((p) => p.uid === uid)
  if (player)
    return {
      label: t('issues.linkPlayer', { name: `${player.first_name} ${player.last_name}`.trim() || unnamed }),
      to: playerPath(playerRef(player)),
    }
  return null
}
