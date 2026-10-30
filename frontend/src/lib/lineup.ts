import type { Lineup, PlayerRef, Team } from '@/api/types'

export const LINEUP_SLOTS = 13 // fs4lineup position0..12
export const modeKey = (players: number, goalkeeper: boolean) => `${players}-${goalkeeper ? 1 : 0}`

/** Player keys of the lineup slot by slot, as the build writes them (builder.lineup_order): given starters,
 * empty or invalid slots filled with the next free player (reserves first, then roster order), then the bench.
 * Keys are strings (String(PlayerRef)); the lineup is given with the same keys. */
export function lineupOrder(
  lineup: { players: number; starters: (string | null)[]; reserves: string[] },
  roster: string[],
): string[] {
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

const GK = 0
const DEFENDERS = new Set([3, 4, 5, 6, 7, 10]) // RB RCB CB LCB LB CDM (catalog.POSITIONS)
const ATTACKERS = new Set([23, 24, 25, 26, 27, 18]) // RW RS ST LS LW CAM
const BENCH = new Set([28, 29]) // SUB RES

/** First lineup of a mode, by position: for each slot area (0 GK, 1 DEF, 2 ATT) the first player of the roster that
 * fits it best (goalkeeper; defenders, then midfielders; attackers, then midfielders), players listed as SUB/RES
 * last; the rest is the bench in roster order. Returns player keys, starters first. */
export function suggestLineup(players: { key: string; position?: number | null }[], areas: number[]): string[] {
  const rank = (area: number, position: number | null | undefined) => {
    if (position == null) return 3
    if (BENCH.has(position)) return 4
    if (area === 0) return position === GK ? 0 : 5
    if (position === GK) return 6 // a goalkeeper only out of goal when nobody else is left
    if (area === 1) return DEFENDERS.has(position) ? 0 : ATTACKERS.has(position) ? 2 : 1
    return ATTACKERS.has(position) ? 0 : DEFENDERS.has(position) ? 2 : 1
  }
  const left = [...players]
  const starters = areas.map((area) => {
    if (!left.length) return null
    const best = left.reduce((a, b) => (rank(area, b.position) < rank(area, a.position) ? b : a))
    left.splice(left.indexOf(best), 1)
    return best.key
  })
  return [...starters.filter((k): k is string => !!k), ...left.map((p) => p.key)]
}

/** Set-piece takers of a team without a player who left it (the role goes back to the captain). */
export function takersWithout(team: Team, uid: PlayerRef): Team['takers'] {
  return team.takers && Object.fromEntries(Object.entries(team.takers).filter(([, p]) => p !== uid))
}

/** The team's lineups without a player (removed from the team or deleted): its slot goes back to automatic. */
export function lineupsWithout(team: Team, uid: PlayerRef): Lineup[] | undefined {
  return team.lineups?.map((l) => ({
    ...l,
    starters: l.starters.map((u) => (u === uid ? null : u)),
    reserves: l.reserves.filter((u) => u !== uid),
  }))
}

/** Lineups of a copied team, with the players' uids mapped to their copies (none when the roster is not copied). */
export function copyLineups(team: Team, uids: Map<string, string>): Lineup[] | undefined {
  if (!team.lineups || uids.size === 0) return undefined
  const map = (u: PlayerRef | null) => (typeof u === 'string' && uids.get(u)) || null
  return team.lineups.map((l) => ({
    ...l,
    starters: l.starters.map(map),
    reserves: l.reserves.map(map).filter((u): u is string => !!u),
  }))
}
