import type { OriginalStadium, StadiumFilter } from '@/api/types'
import type { MessageKey, TFunction as Translate } from '@/i18n'

/** Address of a stadium's page (its first row's stadiumid). */
export const stadiumPath = (id: number) => `/stadiums/${id}`

/** The game's menu modes, by the match setup (fifaStadiumFilter id) that lists their stadiums (seen in game). */
export const GAME_MODES: { filter: number; label: MessageKey }[] = [
  { filter: 11, label: 'stadium.mode5v5' },
  { filter: 0, label: 'stadium.modeFutsal' },
  { filter: 2, label: 'stadium.modePanna' },
  { filter: 16, label: 'stadium.modeLastMan' },
]

/** Label of any match setup: "5 v 5 with goalkeeper", "Futsal", "Last man standing, 3 players"... */
export function filterLabel(f: StadiumFilter, t: Translate) {
  if (f.isfutsal) return t('stadium.modeFutsal')
  if (f.islastmanstanding) return t('stadium.setupLastMan', { n: f.numplayersonpitch })
  return t(f.goalieon ? 'stadium.setupKeeper' : 'stadium.setupNoKeeper', { n: f.numplayersonpitch })
}

/** stadiums.surfacetype: the pitch's floor (the same three as the boots: street, turf, indoor). */
export const SURFACE_LABELS: Record<number, MessageKey> = {
  0: 'stadium.surfaceStreet',
  1: 'stadium.surfaceTurf',
  2: 'stadium.surfaceIndoor',
}

/** stadiums.timeofday: 1 = day, 3 and 4 = night (two different lights, seen in game as night). */
export const TIME_LABELS: Record<number, MessageKey> = { 1: 'stadium.timeDay', 3: 'stadium.timeNight', 4: 'stadium.timeNight' }

/** Kind of goal (stadiums.goaltype): futsal goals, goals with a goalkeeper, small goals without one. */
export function goalLabel(goalType: number, t: Translate) {
  if (goalType <= 2) return t('stadium.goalFutsal', { type: goalType })
  if (goalType <= 14) return t('stadium.goalKeeper', { type: goalType })
  return t('stadium.goalSmall', { type: goalType })
}

/** The game's modes that list a stadium: only one with a row flagged for the menus is listed at all. */
export const modesOf = (s: OriginalStadium) => (s.in_menu ? GAME_MODES.filter((m) => s.filters.includes(m.filter)) : [])

/** The version an ordinary match loads (flagged in the game's table); none flagged: the first, only to have one. */
export const menuVersion = (s: OriginalStadium) => s.versions.find((v) => v.menu) ?? s.versions[0]
