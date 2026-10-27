import type { KitKind, KitPart, Project, RGB, Team } from '@/api/types'
import { useI18n } from '@/i18n'
import { useProject } from '@/state/project'
import { useCatalog, useLookups, useOriginalTeams } from '@/state/queries'

/** Kit colors the builder uses when the team does not override them (same rule as fsmod.model.Team.kit). */
export function defaultKit(team: Team, kind: KitKind): Record<KitPart, RGB> {
  const p = team.primary_color
  const s = team.secondary_color
  return kind === 'home' ? { jersey: p, shorts: s, socks: p } : { jersey: s, shorts: p, socks: s }
}

export function fullKit(team: Team, kind: KitKind): Record<KitPart, RGB> {
  return { ...defaultKit(team, kind), ...team.kits[kind] }
}

export function useLeagueName() {
  const { t } = useI18n()
  const { draft } = useProject()
  const { originalLeague } = useLookups()
  return (league: number | string) =>
    typeof league === 'string'
      ? draft.leagues.find((l) => l.uid === league)?.name || t('league.unnamed')
      : originalLeague.get(league)?.name ?? t('league.byId', { id: league })
}

/** Teams of a league as the game's team selector shows them: the project's (not hidden) + the original ones the
 * project does not hide. Same count as fsmod.validation (league_too_many_teams). */
export function useLeagueTeams() {
  const { draft } = useProject()
  const originals = useOriginalTeams().data ?? []
  const max = useCatalog().data?.max_league_teams ?? 30
  const hidden = new Set(draft.originals?.hidden_teams ?? [])
  const count = (league: number | string) =>
    draft.teams.filter((t) => t.league === league && !t.hidden).length +
    (typeof league === 'number' ? originals.filter((t) => t.league === league && !hidden.has(t.id)).length : 0)
  return { count, max, isFull: (league: number | string) => count(league) >= max }
}

/** Default league for a new team: the first new league with room, else the first visible original league with room
 * (null when every league is full). */
export function defaultLeague(
  project: Project,
  originals: { id: number; hidden: boolean; sort_order: number }[],
  isFull: (league: number | string) => boolean,
) {
  const visible = originals.filter((l) => !l.hidden).sort((a, b) => a.sort_order - b.sort_order)
  const leagues: (number | string)[] = [...project.leagues.map((l) => l.uid), ...visible.map((l) => l.id)]
  return leagues.find((l) => !isFull(l)) ?? null
}
