import type { Glove, Player, Project } from '@/api/types'
import { useProject } from '@/state/project'
import { useCatalog } from '@/state/queries'

/** Address of a glove's page: a new glove by uid, one of the game's by its code (edited or not). */
export const glovePath = (key: string | number) => `/gloves/${key}`
export const gloveKey = (glove: Glove) => glove.original_id ?? glove.uid

export const gloveName = (glove: Glove, unnamed: string) => glove.name.trim() || unnamed

export const GOALKEEPER = 0 // preferredposition1 / team position of the goalkeeper
const NOT_A_POSITION = new Set([28, 29]) // SUB / RES
const FALLBACK_POSITION = 25 // ST

/** The preferred position (players.preferredposition1) the build writes for a player (fsmod.gloves.preferred_position,
 * same rule): the goalkeeper's when a glove was picked (only goalkeepers wear their own glove), otherwise the
 * position he has in most of his teams (a tie: his first team's; SUB/RES and unknown do not count), ST without any.
 * An original player keeps the game's own unless the rule turns him into a goalkeeper or out of one.
 * byGlove: the glove changed the result (without it he would not be a goalkeeper). */
export function preferredPosition(player: Player): { position: number; byGlove: boolean } {
  const position = ruledPosition(player, player.glove != null)
  const byGlove = player.glove != null && ruledPosition(player, false) !== GOALKEEPER
  return { position, byGlove }
}

function ruledPosition(player: Player, glove: boolean): number {
  let computed = FALLBACK_POSITION
  if (glove) computed = GOALKEEPER
  else {
    const positions = player.teams.map((l) => l.position).filter((p): p is number => p != null && !NOT_A_POSITION.has(p))
    if (positions.length) {
      const count = new Map<number, number>()
      positions.forEach((p) => count.set(p, (count.get(p) ?? 0) + 1))
      const best = Math.max(...count.values())
      computed = positions.find((p) => count.get(p) === best)!
    }
  }
  const current = player.original_id != null ? player.fields.preferredposition1 : undefined
  if (current !== undefined && (computed === GOALKEEPER) === (current === GOALKEEPER)) return current
  return computed
}

/** Free codes left for new gloves: `total` (the game's free ones) and how many the project takes (new gloves in the
 * patch), without `except` (the glove being changed). */
export function useGloveSlots(except?: string) {
  const { draft } = useProject()
  const total = useCatalog().data?.gloves.slots ?? 0
  const used = (draft.gloves ?? []).filter((g) => g.original_id == null && !g.hidden && g.uid !== except).length
  return { total, used, free: Math.max(0, total - used) }
}

/** The project's players with a glove picked: a new glove by its uid, one of the game's by its code. */
export const wearers = (project: Project, glove: Glove | { original_id: number }) => {
  const ref = 'uid' in glove && glove.original_id == null ? glove.uid : glove.original_id!
  return project.players.filter((p) => p.glove === ref)
}

/** Gloves of an imported zip made ready to join the project: a glove without its file, or one beyond the free codes,
 * comes in out of the patch (hidden) so the patch still builds. */
export function admitImported(gloves: Glove[], free: number) {
  let left = free
  return gloves.map((g) => {
    let hidden = !!g.hidden || !g.texture
    if (!hidden) {
      if (left > 0) left -= 1
      else hidden = true
    }
    return { ...g, hidden }
  })
}
