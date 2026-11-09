import type { Player } from '@/api/types'

/** bodytypecode = height class x build, as in fsmod.body: 1-3 normal, 4-6 tall, 7-9 short; in each, lean, medium,
 * stocky. In game the height comes from the Height field alone, so the user picks the build and the height picks the
 * class (the build does the same when it writes the patch). */
export const SHORT_UP_TO = 170
export const TALL_FROM = 185
export const BUILDS = ['lean', 'medium', 'stocky'] as const
export type Build = (typeof BUILDS)[number]
export type HeightClass = 'short' | 'normal' | 'tall'

const CLASS_OFFSET: Record<HeightClass, number> = { normal: 0, tall: 3, short: 6 }

export const heightClass = (height: number): HeightClass => (height <= SHORT_UP_TO ? 'short' : height >= TALL_FROM ? 'tall' : 'normal')

/** 0 lean, 1 medium, 2 stocky. */
export const buildOf = (code: number) => (Math.max(code, 1) - 1) % 3

export const bodyCode = (build: number, height: number) => CLASS_OFFSET[heightClass(height)] + build + 1

/** A player patch with the body type moved to the class of the new height (same build). Only an own body type is
 * changed: an inherited one is fitted by the build. */
export function withFittedBody(player: Player, patch: Partial<Player>): Partial<Player> {
  if (!('height' in patch) || patch.height == null) return patch
  const appearance = patch.appearance ?? player.appearance
  const code = appearance.bodytypecode
  if (code === undefined) return patch
  const fitted = bodyCode(buildOf(code), patch.height)
  return fitted === code ? patch : { ...patch, appearance: { ...appearance, bodytypecode: fitted } }
}
