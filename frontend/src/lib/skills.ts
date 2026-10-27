/** Bars averaged into the overall: every bar but TRI (0 to 4 scale) and the overall itself. */
export const OVERALL_SKILLS = ['ATH', 'DEF', 'DRI', 'GK', 'PAS', 'SHO', 'SPE']

/** Overall = rounded average of OVERALL_SKILLS. The game stores it apart and never computes it. */
export function computeOverall(value: (key: string) => number | undefined): number | undefined {
  const values = OVERALL_SKILLS.map(value)
  if (values.some((v) => v === undefined)) return undefined
  return Math.round((values as number[]).reduce((sum, v) => sum + v, 0) / values.length)
}
