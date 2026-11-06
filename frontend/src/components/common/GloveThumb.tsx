import { Hand } from 'lucide-react'
import { useState } from 'react'
import { gloveThumbUrl, originalGloveThumbUrl } from '@/api/client'
import type { Glove } from '@/api/types'
import { cn } from '@/lib/utils'

/** List picture of a glove: a project glove's own picture or its file drawn by the backend; one of the game's gloves
 * (or an edited one without a file of its own) drawn from the game's files. */
export function GloveThumb({ glove, code, className }: { glove?: Glove; code?: number; className?: string }) {
  const own = glove ? gloveThumbUrl(glove) : undefined
  const gameCode = code ?? (glove?.original_id ?? undefined)
  const src = own ?? (gameCode != null ? originalGloveThumbUrl(gameCode) : undefined)
  const [failed, setFailed] = useState<string>()
  return (
    <span className={cn('inline-flex size-9 shrink-0 items-center justify-center overflow-hidden rounded bg-muted', className)}>
      {src && failed !== src ? (
        <img src={src} alt="" loading="lazy" className="size-full object-contain" onError={() => setFailed(src)} />
      ) : (
        <Hand className="size-4 text-muted-foreground/60" />
      )}
    </span>
  )
}
