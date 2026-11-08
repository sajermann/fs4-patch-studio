import { Volleyball } from 'lucide-react'
import { useState } from 'react'
import { ballThumbUrl, originalBallThumbUrl } from '@/api/client'
import type { Ball } from '@/api/types'
import { cn } from '@/lib/utils'

/** List picture of a ball: a project ball's own picture or its files drawn by the backend; one of the game's balls
 * (or an edited one without files of its own) drawn from the game's files. */
export function BallThumb({ ball, id, className }: { ball?: Ball; id?: number; className?: string }) {
  const own = ball ? ballThumbUrl(ball) : undefined
  const gameId = id ?? (ball?.original_id ?? undefined)
  const src = own ?? (gameId != null ? originalBallThumbUrl(gameId) : undefined)
  const [failed, setFailed] = useState<string>()
  return (
    <span className={cn('inline-flex size-9 shrink-0 items-center justify-center overflow-hidden rounded bg-muted', className)}>
      {src && failed !== src ? (
        <img src={src} alt="" loading="lazy" className="size-full object-contain" onError={() => setFailed(src)} />
      ) : (
        <Volleyball className="size-4 text-muted-foreground/60" />
      )}
    </span>
  )
}
