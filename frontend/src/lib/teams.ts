import type { KitKind, KitPart, PlayerRef, Project, RGB, TakerRole, Team } from '@/api/types'
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
  const edited = editedOriginals(draft)
  const count = (league: number | string) =>
    draft.teams.filter(
      (t) => t.league === league && !t.hidden && !(t.original_id != null && hidden.has(t.original_id)),
    ).length +
    (typeof league === 'number'
      ? originals.filter((t) => t.league === league && !hidden.has(t.id) && !edited.has(t.id)).length
      : 0)
  return { count, max, isFull: (league: number | string) => count(league) >= max }
}

/** Original teams the project edits in place (Team.original_id), by teamid. */
export function editedOriginals(project: Project): Map<number, Team> {
  return new Map(project.teams.filter((t) => t.original_id != null).map((t) => [t.original_id!, t]))
}

export const isOriginalTeam = (team: Team) => team.original_id != null

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

export type Role = 'captain' | TakerRole
const TAKER_ROLES: TakerRole[] = ['penalty', 'free_kick', 'long_free_kick', 'left_corner', 'right_corner']

/** Who has each role, with the fallbacks applied: a taker role left unset is the captain's. */
export function effectiveRoles(
  captain: PlayerRef | undefined,
  takers: Partial<Record<TakerRole, PlayerRef>>,
): Record<Role, PlayerRef | undefined> {
  return { captain, ...Object.fromEntries(TAKER_ROLES.map((r) => [r, takers[r] ?? captain])) } as Record<Role, PlayerRef | undefined>
}
