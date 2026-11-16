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

/** The same label and page for every league/team/player of the project, by uid (built once for a whole list). */
export function entityLinks(t: TFunction, project: Project) {
  const unnamed = t('common.unnamed')
  const links = new Map<string, { label: string; to: string }>()
  for (const p of project.players)
    links.set(p.uid, {
      label: t('issues.linkPlayer', { name: `${p.first_name} ${p.last_name}`.trim() || unnamed }),
      to: playerPath(playerRef(p)),
    })
  for (const tm of project.teams) links.set(tm.uid, { label: t('issues.linkTeam', { name: tm.name || unnamed }), to: teamPath(teamKey(tm)) })
  for (const l of project.leagues) links.set(l.uid, { label: t('issues.linkLeague', { name: l.name || unnamed }), to: leaguePath(leagueKey(l)) })
  return links
}
