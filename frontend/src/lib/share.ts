import type { Ball, Boot, Glove, League, Player, Project, ShareKind, Team } from '@/api/types'

/** Leagues, teams and players shared in a zip (backend share_service). Each entry goes alone with the links it keeps:
 * on import the links that point to an entry the project does not have are listed and dropped (a player's teams,
 * boots and glove; a team's leagues), except a team's captain, takers and lineups, kept for the players that come
 * next (the validator flags them until then). Uids are kept: an entry already in the project is replaced. */

/** What a zip can bring: leagues, teams and players (share_service) and boots, gloves and balls (their own zips, which
 * keep uid and original_id the same way; they point to nothing, so they only replace). */
export type ImportKind = ShareKind | 'boots' | 'gloves' | 'balls'
export type SharedEntry = League | Team | Player | Boot | Glove | Ball
export const entriesOf = (project: Project, kind: ImportKind): SharedEntry[] => project[kind] ?? []

export type MissingLink =
  | { kind: 'team'; ref: string }
  | { kind: 'league'; ref: string }
  | { kind: 'boot'; ref: string }
  | { kind: 'glove'; ref: string }

export interface ShareAnalysis {
  /** project entry each incoming one replaces (same uid, or the same game entry edited) */
  replaces: Map<string, SharedEntry>
  /** links of each incoming entry to entries the project does not have (dropped on import) */
  missing: Map<string, MissingLink[]>
  /** incoming teams whose captain, takers or lineup name players the project does not have yet (kept) */
  waitingPlayers: Set<string>
}

export const entryName = (kind: ImportKind, e: SharedEntry) =>
  kind === 'players'
    ? (e as Player).display_name || `${(e as Player).first_name} ${(e as Player).last_name}`.trim()
    : (e as Exclude<SharedEntry, Player>).name.trim()

/** Player refs a team names (captain, takers, lineups). */
function playerRefs(team: Team) {
  const refs = new Set<string | number>()
  if (team.captain != null) refs.add(team.captain)
  Object.values(team.takers ?? {}).forEach((r) => r != null && refs.add(r))
  for (const l of team.lineups ?? []) {
    l.starters.forEach((r) => r != null && refs.add(r))
    l.reserves.forEach((r) => refs.add(r))
  }
  return refs
}

export function analyzeShare(kind: ImportKind, project: Project, items: SharedEntry[]): ShareAnalysis {
  const replaces = new Map<string, SharedEntry>()
  const missing = new Map<string, MissingLink[]>()
  const waitingPlayers = new Set<string>()
  const existing = entriesOf(project, kind)
  const newLeagues = new Set(project.leagues.filter((l) => l.original_id == null).map((l) => l.uid))
  const newTeams = new Set(project.teams.filter((t) => t.original_id == null).map((t) => t.uid))
  const newPlayers = new Set(project.players.filter((p) => p.original_id == null).map((p) => p.uid))
  const boots = new Set((project.boots ?? []).map((b) => b.uid))
  const gloves = new Set((project.gloves ?? []).map((g) => g.uid))
  for (const item of items) {
    const same = existing.find((e) => e.uid === item.uid || (item.original_id != null && e.original_id === item.original_id))
    if (same) replaces.set(item.uid, same)
    const lost: MissingLink[] = []
    if (kind === 'teams') {
      const team = item as Team
      team.leagues.forEach((l) => typeof l === 'string' && !newLeagues.has(l) && lost.push({ kind: 'league', ref: l }))
      if ([...playerRefs(team)].some((r) => typeof r === 'string' && !newPlayers.has(r))) waitingPlayers.add(team.uid)
    } else if (kind === 'players') {
      const player = item as Player
      player.teams.forEach((l) => typeof l.team === 'string' && !newTeams.has(l.team) && lost.push({ kind: 'team', ref: l.team }))
      Object.values(player.boots ?? {}).forEach((b) => b && !boots.has(b) && lost.push({ kind: 'boot', ref: b }))
      if (typeof player.glove === 'string' && !gloves.has(player.glove)) lost.push({ kind: 'glove', ref: player.glove })
    }
    if (lost.length) missing.set(item.uid, lost)
  }
  return { replaces, missing, waitingPlayers }
}

/** The entry without the links the project does not have. */
export function withoutMissing(kind: ImportKind, item: SharedEntry, lost: MissingLink[] | undefined): SharedEntry {
  if (!lost?.length) return item
  const gone = (k: MissingLink['kind'], ref: unknown) => lost.some((m) => m.kind === k && m.ref === ref)
  if (kind === 'teams') {
    const team = item as Team
    return { ...team, leagues: team.leagues.filter((l) => !gone('league', l)) }
  }
  const player = item as Player
  return {
    ...player,
    teams: player.teams.filter((l) => !gone('team', l.team)),
    boots: player.boots && Object.fromEntries(Object.entries(player.boots).filter(([, b]) => !gone('boot', b))),
    glove: gone('glove', player.glove) ? undefined : player.glove,
  }
}

/** The project with the imported entries: each one takes the place of the entry it replaces (or goes at the end),
 * without the links the project does not have. */
export function mergeShared(kind: ImportKind, project: Project, items: SharedEntry[], analysis: ShareAnalysis): Project {
  let list = [...entriesOf(project, kind)]
  for (const raw of items) {
    const item = withoutMissing(kind, raw, analysis.missing.get(raw.uid))
    const at = list.findIndex((e) => e.uid === item.uid || (item.original_id != null && e.original_id === item.original_id))
    if (at >= 0) {
      list[at] = item
      list = list.filter((e, k) => k === at || !(e.uid === item.uid || (item.original_id != null && e.original_id === item.original_id)))
    } else list.push(item)
  }
  return { ...project, [kind]: list }
}

/** What a zip uploaded on an entry's page does with that entry (`entry`, the one the page shows):
 * - the page is creating it (not saved yet, not a game entry): the zip's entry takes its place, with the zip's uid;
 *   a zip of an edited game entry turns it into that edit (refused when the project already edits it);
 * - the page edits it (saved, or a game entry): the zip fills it after the user says so (it keeps its own uid); a
 *   zip of another game entry, or of a new entry on a game entry's page, is refused;
 * - the zip's uid belongs to another entry of the project: refused (that entry is updated on its own page). */
export type SinglePlan =
  | { ok: true; mode: 'create' | 'edit'; uid: string }
  | { ok: false; reason: 'uidTaken' | 'originalEdited' | 'otherOriginal' | 'newIntoOriginal'; other?: SharedEntry }

export function planSingle(kind: ImportKind, project: Project, saved: Set<string>, entry: SharedEntry, incoming: SharedEntry): SinglePlan {
  const others = entriesOf(project, kind).filter((e) => e.uid !== entry.uid)
  const creating = entry.original_id == null && !saved.has(entry.uid)
  const owner = others.find((e) => e.uid === incoming.uid)
  if (incoming.original_id != null) {
    if (entry.original_id === incoming.original_id) return { ok: true, mode: 'edit', uid: entry.uid }
    if (!creating) return { ok: false, reason: 'otherOriginal' }
    const editing = others.find((e) => e.original_id === incoming.original_id)
    if (editing) return { ok: false, reason: 'originalEdited', other: editing }
    return { ok: true, mode: 'create', uid: owner ? entry.uid : incoming.uid }
  }
  if (entry.original_id != null) return { ok: false, reason: 'newIntoOriginal' }
  if (owner) return { ok: false, reason: 'uidTaken', other: owner }
  return creating ? { ok: true, mode: 'create', uid: incoming.uid } : { ok: true, mode: 'edit', uid: entry.uid }
}

/** The project with the page's entry (`uid`) replaced by the imported one, without the links the project lacks. */
export function replaceEntry(kind: ImportKind, project: Project, uid: string, item: SharedEntry, analysis: ShareAnalysis, zipUid: string): Project {
  const clean = { ...withoutMissing(kind, { ...item, uid: zipUid }, analysis.missing.get(zipUid)), uid: item.uid }
  return { ...project, [kind]: entriesOf(project, kind).map((e) => (e.uid === uid ? clean : e)) }
}
