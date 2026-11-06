import { Footprints } from 'lucide-react'
import { useState } from 'react'
import { bootThumbUrl, originalBootThumbUrl } from '@/api/client'
import type { Boot } from '@/api/types'
import { cn } from '@/lib/utils'

/** List picture of a boot: a project boot's own picture or its files drawn by the backend; one of the game's boots
 * (or an edited one without files of its own) drawn from the game's files. */
export function BootThumb({ boot, code, className }: { boot?: Boot; code?: number; className?: string }) {
  const own = boot ? bootThumbUrl(boot) : undefined
  const gameCode = code ?? (boot?.original_id ?? undefined)
  const src = own ?? (gameCode != null ? originalBootThumbUrl(gameCode) : undefined)
  const [failed, setFailed] = useState<string>()
  return (
    <span className={cn('inline-flex h-7 w-14 shrink-0 items-center justify-center overflow-hidden rounded bg-muted', className)}>
      {src && failed !== src ? (
        <img src={src} alt="" loading="lazy" className="size-full object-contain" onError={() => setFailed(src)} />
      ) : (
        <Footprints className="size-4 text-muted-foreground/60" />
      )}
    </span>
  )
}
