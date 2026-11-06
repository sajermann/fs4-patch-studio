import { SHOE_SURFACES, SURFACE_FIELDS, type Boot, type Player, type Project, type ShoeSurface } from '@/api/types'
import type { MessageKey } from '@/i18n'
import { useProject } from '@/state/project'
import { useCatalog } from '@/state/queries'

/** Address of a boot's page: a new boot by uid, one of the game's by its code (edited or not). */
export const bootPath = (key: string | number) => `/boots/${key}`
export const bootKey = (boot: Boot) => boot.original_id ?? boot.uid

export const SURFACE_LABELS: Record<ShoeSurface, MessageKey> = {
  street: 'boots.surfaceStreet',
  turf: 'boots.surfaceTurf',
  indoor: 'boots.surfaceIndoor',
}

/** The game takes these codes on the street (STREET_CODES of the backend). */
export const streetCode = (code: number) => code >= 500 && code <= 619

/** New boots of the project that take a street code (the ones in the patch). */
export const streetBoots = (project: Project) => (project.boots ?? []).filter((b) => b.original_id == null && b.street && !b.hidden)

/** Free street codes left for new boots: `total` (the game's free ones) and how many the project takes, without
 * `except` (the boot being changed). */
export function useStreetSlots(except?: string) {
  const { draft } = useProject()
  const total = useCatalog().data?.boots.street_slots ?? 0
  const used = streetBoots(draft).filter((b) => b.uid !== except).length
  return { total, used, free: Math.max(0, total - used) }
}

/** Surfaces on which a player wears a boot: a new boot by its uid (Player.boots), one of the game's by its code (the
 * player's appearance code on a surface he does not override). */
export function surfacesOf(player: Player, boot: Boot | { original_id: number }): ShoeSurface[] {
  const own = player.boots ?? {}
  if ('uid' in boot && boot.original_id == null) return SHOE_SURFACES.filter((s) => own[s] === boot.uid)
  return SHOE_SURFACES.filter((s) => !own[s] && player.appearance[SURFACE_FIELDS[s]] === boot.original_id)
}

/** The project's players wearing a boot, with the surfaces. */
export const wearers = (project: Project, boot: Boot | { original_id: number }) =>
  project.players.map((player) => ({ player, surfaces: surfacesOf(player, boot) })).filter((w) => w.surfaces.length)

export const bootName = (boot: Boot, unnamed: string) => boot.name.trim() || unnamed

/** Boots of an imported zip made ready to join the project: a boot without its files, or that may go on the street
 * when no street code is left, comes in out of the patch (hidden) so the patch still builds; showing it again
 * checks the street codes. */
export function admitImported(boots: Boot[], freeStreet: number) {
  let free = freeStreet
  return boots.map((b) => {
    const complete = !!(b.mesh && b.texture)
    let hidden = !!b.hidden || !complete
    if (b.street && !hidden) {
      if (free > 0) free -= 1
      else hidden = true
    }
    return { ...b, hidden }
  })
}
