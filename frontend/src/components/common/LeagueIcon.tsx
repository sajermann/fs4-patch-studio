import { Trophy } from 'lucide-react'
import { imageUrl, originalLeagueImageUrl } from '@/api/client'
import type { LeagueKey } from '@/api/types'
import { linkedLeague } from '@/lib/players'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'

/** A league's image as the selector shows it: the project's image (new league or edited original), the game's flag
 * of an original league, or a trophy when there is none. */
export function LeagueIcon({ league, className }: { league: LeagueKey; className?: string }) {
  const { draft } = useProject()
  const entry = linkedLeague(draft, league)
  const src = entry?.image ? imageUrl(entry.image) : typeof league === 'number' ? originalLeagueImageUrl(league) : null
  return src ? (
    <img src={src} alt="" loading="lazy" className={cn('size-8 rounded-sm object-contain', className)} />
  ) : (
    <span className={cn('flex size-8 items-center justify-center rounded-sm border text-muted-foreground', className)}>
      <Trophy className="size-4" />
    </span>
  )
}
