import type { Ball, OriginalBall, OriginalStadium, Project, StadiumVersion } from '@/api/types'
import type { MessageKey } from '@/i18n'
import { useProject } from '@/state/project'
import { useCatalog } from '@/state/queries'

/** Address of a ball's page: a new ball by uid, one of the game's by its id (edited or not). */
export const ballPath = (key: string | number) => `/balls/${key}`
export const ballKey = (ball: Ball) => ball.original_id ?? ball.uid

export const ballName = (ball: Ball, unnamed: string) => ball.name.trim() || unnamed

/** Name of one of the game's balls: the game's own text, or "Ball <id>" (most street balls have none). */
export const gameBallName = (ball: Pick<OriginalBall, 'id' | 'name'> | undefined, id: number, fallback: (id: number) => string) =>
  ball?.name || fallback(id)

/** renderingregionid of a stadium's country versions (fsmod catalog); -1 = a stadium without versions. */
export const REGION_LABELS: Record<number, MessageKey> = {
  1: 'stadium.regionUs',
  2: 'stadium.regionEngland',
  3: 'stadium.regionFrance',
  4: 'stadium.regionItaly',
  5: 'stadium.regionGermany',
  6: 'stadium.regionSpain',
  7: 'stadium.regionCanada',
}

/** Free ids left for new balls: `total` (the game's free ones) and how many the project takes (new balls in the
 * patch), without `except` (the ball being changed). */
export function useBallSlots(except?: string) {
  const { draft } = useProject()
  const total = useCatalog().data?.balls.slots ?? 0
  const used = (draft.balls ?? []).filter((b) => b.original_id == null && !b.hidden && b.uid !== except).length
  return { total, used, free: Math.max(0, total - used) }
}

/** The ball a stadium row has in the project: the user's pick (a new ball's uid or a game ball's id), else the game's. */
export const pickedBall = (project: Project, version: StadiumVersion): string | number =>
  project.originals?.stadium_balls?.[version.id] ?? version.ball

/** Stadium rows (with their stadium) that use a ball in the project: a new ball by its uid; one of the game's by its
 * id, picked by the user or the game's own (`picked` says which). */
export function stadiumsUsing(project: Project, stadiums: OriginalStadium[], ball: Ball | { original_id: number }) {
  const ref = 'uid' in ball && ball.original_id == null ? ball.uid : ball.original_id!
  const picked = project.originals?.stadium_balls ?? {}
  return stadiums.flatMap((stadium) =>
    stadium.versions
      .filter((v) => pickedBall(project, v) === ref)
      .map((version) => ({ stadium, version, picked: version.id in picked })),
  )
}

/** Balls of an imported zip made ready to join the project: a ball without both files, or one beyond the free ids,
 * comes in out of the patch (hidden) so the patch still builds. */
export function admitImported(balls: Ball[], free: number) {
  let left = free
  return balls.map((b) => {
    let hidden = !!b.hidden || !(b.mesh && b.texture)
    if (!hidden) {
      if (left > 0) left -= 1
      else hidden = true
    }
    return { ...b, hidden }
  })
}
