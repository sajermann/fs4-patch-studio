import type { KitKind, KitPart, League, LeagueKey, PlayerRef, Project, RGB, TakerRole, Team } from '@/api/types'
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

/** Name of a team's league: a new league, one of the game's (its edited name when edited) or "no league". */
export function useLeagueName() {
  const { t } = useI18n()
  const { draft } = useProject()
  const { originalLeague } = useLookups()
  return (league: LeagueKey | null) =>
    league === null
      ? t('teams.noLeague')
      : typeof league === 'string'
        ? draft.leagues.find((l) => l.uid === league)?.name || t('league.unnamed')
        : draft.leagues.find((l) => l.original_id === league)?.name ||
          (originalLeague.get(league)?.name ?? t('league.byId', { id: league }))
}

/** The project's new leagues (entries that edit one of the game's leagues left out). */
export const newLeagues = (project: Project): League[] => project.leagues.filter((l) => l.original_id == null)

/** The team is left out of the patch in this league only (Team.hidden_in_leagues): it stays in the league in the app. */
export const hiddenInLeague = (team: Team, league: LeagueKey) => !!team.hidden_in_leagues?.includes(league)

/** The team with one of its leagues shown or hidden in the patch (Team.hidden_in_leagues). */
export function withLeagueShown(team: Team, league: LeagueKey, shown: boolean): Team {
  const rest = (team.hidden_in_leagues ?? []).filter((l) => l !== league)
  return { ...team, hidden_in_leagues: shown ? rest : [...rest, league] }
}

/** Teams of a league in the patch, as the game's team selector shows them: the project's (not hidden, not hidden in
 * that league) + the original ones the project does not hide. Same count as fsmod.validation
 * (league_too_many_teams). total: every team in the league in the app, out of the patch there or not. */
export function leagueTeamCount(project: Project, originals: { id: number; league: number | null }[]) {
  const hidden = new Set(project.originals?.hidden_teams ?? [])
  const edited = editedOriginals(project)
  const inLeague = (league: LeagueKey, patchOnly: boolean) =>
    project.teams.filter(
      (t) =>
        t.leagues.includes(league) &&
        !(patchOnly && (t.hidden || hiddenInLeague(t, league) || (t.original_id != null && hidden.has(t.original_id)))),
    ).length +
    (typeof league === 'number'
      ? originals.filter((t) => t.league === league && !edited.has(t.id) && !(patchOnly && hidden.has(t.id))).length
      : 0)
  return { count: (league: LeagueKey) => inLeague(league, true), total: (league: LeagueKey) => inLeague(league, false) }
}

export function useLeagueTeams() {
  const { draft } = useProject()
  const originals = useOriginalTeams().data ?? []
  const max = useCatalog().data?.max_league_teams ?? 30
  const { count, total } = leagueTeamCount(draft, originals)
  return { count, total, max, isFull: (league: LeagueKey) => count(league) >= max }
}

/** Teams that came in a shared zip fitted to the patch limit of their leagues (no dialog): in each league they joined,
 * the ones already in the project keep how they were; the newcomers fill the places left up to max, in the zip's
 * order, and the others join hidden in that league. */
export function fitImportedLeagues(
  before: Project,
  after: Project,
  imported: string[],
  originals: { id: number; league: number | null }[],
  max: number,
): Project {
  const was = (t: Team) => before.teams.find((b) => b.uid === t.uid || (t.original_id != null && b.original_id === t.original_id))
  let project = after
  const order = imported.map((uid) => after.teams.find((t) => t.uid === uid)).filter((t): t is Team => !!t)
  for (const team of order) {
    const old = was(team)
    let current = project.teams.find((t) => t.uid === team.uid)!
    for (const league of current.leagues) {
      if (old?.leagues.includes(league)) {
        current = withLeagueShown(current, league, !hiddenInLeague(old, league)) // as it was
        continue
      }
      if (current.hidden || hiddenInLeague(current, league)) continue
      const others = { ...project, teams: project.teams.filter((t) => t.uid !== current.uid) }
      if (leagueTeamCount(others, originals).count(league) >= max) current = withLeagueShown(current, league, false)
    }
    const done = current
    project = { ...project, teams: project.teams.map((t) => (t.uid === done.uid ? done : t)) }
  }
  return project
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
  const leagues: LeagueKey[] = [...newLeagues(project).map((l) => l.uid), ...visible.map((l) => l.id)]
  return leagues.find((l) => !isFull(l)) ?? null
}

export type Role = 'captain' | TakerRole
const TAKER_ROLES: TakerRole[] = ['penalty', 'free_kick', 'long_free_kick', 'left_corner', 'right_corner']

export const GOALKEEPER = 0 // position of the goalkeeper

/** Who takes a set piece nobody was given (as the build does): the captain, unless he is the goalkeeper (a goalkeeper
 * takes one only when chosen); then the first outfield player of the roster, else the captain. */
export function setPieceFallback(captain: PlayerRef | undefined, roster: { ref: PlayerRef; position?: number | null }[]) {
  const position = (ref: PlayerRef | undefined) => roster.find((m) => m.ref === ref)?.position
  if (position(captain) !== GOALKEEPER) return captain
  return roster.find((m) => m.position != null && m.position !== GOALKEEPER)?.ref ?? captain
}

/** Who has each role, with the fallbacks applied: a taker role left unset is `unset`'s (default: the captain). */
export function effectiveRoles(
  captain: PlayerRef | undefined,
  takers: Partial<Record<TakerRole, PlayerRef>>,
  unset: PlayerRef | undefined = captain,
): Record<Role, PlayerRef | undefined> {
  return { captain, ...Object.fromEntries(TAKER_ROLES.map((r) => [r, takers[r] ?? unset])) } as Record<Role, PlayerRef | undefined>
}
