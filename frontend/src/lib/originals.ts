import type { OriginalChanges, OriginalStadium, OriginalTeam } from '@/api/types'
import { useProject } from '@/state/project'

const EMPTY: Required<OriginalChanges> = { hidden_leagues: [], hidden_teams: [], team_locks: {}, stadium_locks: {} }

/** Hide / lock changes to the game's own leagues, teams and stadiums (project.originals). Locks are stored only
 * when they differ from the game. */
export function useOriginalChanges() {
  const { draft, setDraft } = useProject()
  const changes = { ...EMPTY, ...draft.originals }

  const update = (patch: Partial<OriginalChanges>) => setDraft((p) => ({ ...p, originals: { ...EMPTY, ...p.originals, ...patch } }))
  const toggle = (list: number[], id: number) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
  const setLock = (locks: Record<string, boolean>, id: number, locked: boolean, original: boolean) => {
    const next = { ...locks }
    if (locked === original) delete next[id]
    else next[id] = locked
    return next
  }

  return {
    isLeagueHidden: (id: number) => changes.hidden_leagues.includes(id),
    toggleLeague: (id: number) => update({ hidden_leagues: toggle(changes.hidden_leagues, id) }),
    isTeamHidden: (id: number) => changes.hidden_teams.includes(id),
    toggleTeam: (id: number) => update({ hidden_teams: toggle(changes.hidden_teams, id) }),
    teamLocked: (t: OriginalTeam) => changes.team_locks[t.id] ?? t.locked,
    setTeamLocked: (t: OriginalTeam, locked: boolean) => update({ team_locks: setLock(changes.team_locks, t.id, locked, t.locked) }),
    stadiumLocked: (s: OriginalStadium) => changes.stadium_locks[s.id] ?? s.locked,
    setStadiumLocked: (s: OriginalStadium, locked: boolean) =>
      update({ stadium_locks: setLock(changes.stadium_locks, s.id, locked, s.locked) }),
  }
}
