import type { Lineup, Team } from '@/api/types'

export const LINEUP_SLOTS = 13 // fs4lineup position0..12
export const modeKey = (players: number, goalkeeper: boolean) => `${players}-${goalkeeper ? 1 : 0}`

/** Player uids of the lineup slot by slot, as the build writes them (builder.lineup_order): given starters,
 * empty or invalid slots filled with the next free player (reserves first, then roster order), then the bench. */
export function lineupOrder(lineup: Lineup, roster: string[]): string[] {
  const inRoster = new Set(roster)
  const used = new Set<string>()
  const starters = lineup.starters.slice(0, lineup.players).map((u) => {
    const ok = !!u && inRoster.has(u) && !used.has(u)
    if (ok) used.add(u!)
    return ok ? u : null
  })
  const pool = [...new Set([...lineup.reserves, ...roster].filter((u) => inRoster.has(u) && !used.has(u)))]
  const order = starters.map((u) => u ?? pool.shift() ?? null).filter((u): u is string => !!u)
  return [...order, ...pool].slice(0, LINEUP_SLOTS)
}

/** The team's lineups without a player (removed from the team or deleted): its slot goes back to automatic. */
export function lineupsWithout(team: Team, uid: string): Lineup[] | undefined {
  return team.lineups?.map((l) => ({
    ...l,
    starters: l.starters.map((u) => (u === uid ? null : u)),
    reserves: l.reserves.filter((u) => u !== uid),
  }))
}

/** Lineups of a copied team, with the players' uids mapped to their copies (none when the roster is not copied). */
export function copyLineups(team: Team, uids: Map<string, string>): Lineup[] | undefined {
  if (!team.lineups || uids.size === 0) return undefined
  const map = (u: string | null) => (u && uids.get(u)) ?? null
  return team.lineups.map((l) => ({
    ...l,
    starters: l.starters.map(map),
    reserves: l.reserves.map(map).filter((u): u is string => !!u),
  }))
}
