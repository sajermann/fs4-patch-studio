import type { League, LeagueKey, Player, PlayerRef, Project, Team, TeamKey, TeamLink } from '@/api/types'
import { lineupsWithout, takersWithout } from '@/lib/lineup'

/** What a TeamLink names a team by: the uid of a new team, the teamid of an original one (fsmod.model.Team.key). */
export const teamKey = (team: Team): TeamKey => team.original_id ?? team.uid

export const linkOf = (player: Player, team: TeamKey): TeamLink | undefined => player.teams.find((l) => l.team === team)

/** The project's players of a team (new team uid or the game's teamid), in project order. */
export const rosterOf = (project: Project, team: TeamKey) => project.players.filter((p) => !!linkOf(p, team))

/** The player's teams without one (its captain/taker/lineup places are cleaned by the caller). */
export const teamsWithout = (player: Player, team: TeamKey) => player.teams.filter((l) => l.team !== team)

/** The player's teams with one link changed. */
export const teamsWith = (player: Player, team: TeamKey, patch: Partial<TeamLink>) =>
  player.teams.map((l) => (l.team === team ? { ...l, ...patch } : l))

/** Edit page addresses: an original team/player by its game id (opened from the game when not in the project yet),
 * a new one by its uid. Stable, so a reload or a copied link finds it again. */
export const teamPath = (team: TeamKey) => `/teams/${team}`
export const leaguePath = (league: LeagueKey) => `/leagues/${league}`
/** What a team names a league by: the uid of a new league, the leagueid of an original one. */
export const leagueKey = (league: League): LeagueKey => league.original_id ?? league.uid
/** The project League a team's league points to: a new league by uid, an edited original by leagueid. */
export const linkedLeague = (project: Project, league: LeagueKey) =>
  project.leagues.find((l) => (typeof league === 'string' ? l.uid === league : l.original_id === league))
export const playerPath = (player: PlayerRef) => `/players/${player}`
/** The TeamKey/PlayerRef an edit page address names (digits = the game's id). */
export const keyOfPath = (param: string | undefined): string | number | undefined =>
  param === undefined ? undefined : /^\d+$/.test(param) ? Number(param) : param

/** The project Team a link points to: a new team by uid, an edited original by teamid (undefined: not in the project). */
export const linkedTeam = (project: Project, team: TeamKey) =>
  project.teams.find((t) => (typeof team === 'string' ? t.uid === team : t.original_id === team))

/** Smallest shirt number from 1 that is not used. */
export const firstFreeNumber = (used: Iterable<number | null | undefined>) => {
  const taken = new Set(used)
  return Array.from({ length: 99 }, (_, i) => i + 1).find((n) => !taken.has(n))
}

/** Numbers taken in a team by the project's players linked to it. */
export const numbersIn = (project: Project, team: TeamKey) => rosterOf(project, team).map((p) => linkOf(p, team)?.number)

export const playerName = (p: Player, unnamed: string) => p.display_name || `${p.first_name} ${p.last_name}`.trim() || unnamed

/** What lineups, captains and takers name a player by: the uid of a new player, the playerid of one of the game's
 * (edited or not; fsmod.model.Player.ref). */
export const playerRef = (p: Player): PlayerRef => p.original_id ?? p.uid

/** The project's entry of a player ref: a new player by uid, an edited game player by playerid. */
export const playerOf = (project: Project, ref: PlayerRef) =>
  project.players.find((p) => (typeof ref === 'string' ? p.uid === ref : p.original_id === ref))

/** The project with a player out of a team: his link (the game's players need an entry first, see useGamePlayerEntry)
 * and his captain, set-piece and lineup places in that team's entry. */
export function leaveTeam(project: Project, ref: PlayerRef, team: TeamKey): Project {
  const entry = linkedTeam(project, team)
  const player = playerOf(project, ref)
  return {
    ...project,
    players: project.players.map((p) => (p === player ? { ...p, teams: teamsWithout(p, team) } : p)),
    teams: project.teams.map((t) =>
      t !== entry
        ? t
        : {
            ...t,
            captain: t.captain === ref ? undefined : t.captain,
            takers: takersWithout(t, ref),
            lineups: lineupsWithout(t, ref),
          },
    ),
  }
}

/** The project after `ref` took the place of `left` in a team: captain, set-piece and lineup places of the player
 * who left go to `ref` in that team's entry (a team of the game without an entry: the build gives them). */
export function takePlace(project: Project, team: TeamKey, left: PlayerRef, ref: PlayerRef): Project {
  const entry = linkedTeam(project, team)
  if (!entry) return project
  const swap = <T extends PlayerRef | null | undefined>(u: T) => (u === left ? ref : u)
  return {
    ...project,
    teams: project.teams.map((t) =>
      t !== entry
        ? t
        : {
            ...t,
            captain: swap(t.captain),
            takers: t.takers && Object.fromEntries(Object.entries(t.takers).map(([r, p]) => [r, swap(p)])),
            lineups: t.lineups?.map((l) => ({ ...l, starters: l.starters.map(swap), reserves: l.reserves.map(swap) })),
          },
    ),
  }
}
