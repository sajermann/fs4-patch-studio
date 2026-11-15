import { useQuery } from '@tanstack/react-query'
import { Check, Circle, Loader2, Square } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { BuildItemKind, BuildStep } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n, type MessageKey } from '@/i18n'
import { logClientError } from '@/lib/clientLog'
import { clock } from '@/lib/clock'
import { cn } from '@/lib/utils'

const STEP_LABELS: Record<BuildStep, MessageKey> = {
  database: 'build.stepDatabase',
  leagues: 'build.stepLeagues',
  teams: 'build.stepTeams',
  images: 'build.stepImages',
  texts: 'build.stepTexts',
  files: 'build.stepFiles',
}
const ITEM_LABELS: Record<BuildItemKind, MessageKey> = {
  face: 'build.itemFace',
  kit: 'build.itemKit',
  crest: 'build.itemCrest',
  photo: 'build.itemPhoto',
  player: 'build.itemPlayer',
  team: 'build.itemTeam',
}
const POLL_MS = 500

/** Step by step progress of "Gerar patch", polled from the backend while `open` (it cannot be closed meanwhile).
 * "Parar" asks the backend to stop: what was converted stays in the build cache, so building again continues. */
export function BuildProgressDialog({ open }: { open: boolean }) {
  const { t } = useI18n()
  const [asked, setAsked] = useState(false)
  const [seen, setSeen] = useState(false) // this build answered at least once (the data is not the previous one's)
  const { data } = useQuery({
    queryKey: ['patch-progress'],
    queryFn: api.buildProgress,
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
    gcTime: 0,
  })
  if (open && !seen && data?.running) setSeen(true)
  if (!open && (asked || seen)) {
    setAsked(false) // the next build starts with the button available
    setSeen(false)
  }
  // until the first answer of this build arrives, show it starting (not the previous build); once it ended, the
  // dialog stays a moment while the screen reloads the project: show it complete, not back at zero
  const prog = data?.running || (seen && data) ? data : undefined
  const finished = !!prog && !prog.running
  const current = finished ? prog.steps.length : prog?.step ? prog.steps.indexOf(prog.step) : -1
  const stepShare = prog?.total && !finished ? prog.done / prog.total : 0
  const overall = prog ? Math.round(((Math.max(current, 0) + stepShare) / prog.steps.length) * 100) : 0
  const stopping = !finished && (asked || !!prog?.stopping)
  const cache = prog?.cache

  const stop = () => {
    setAsked(true)
    api.cancelBuild().catch((e) => logClientError('cancel build', e))
  }

  return (
    <Dialog open={open}>
      <DialogContent className="sm:max-w-xl" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('build.title')}</DialogTitle>
          <DialogDescription>{t('build.description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{overall}%</span>
            <span>{prog?.elapsed !== undefined ? clock(prog.elapsed) : '0:00'}</span>
          </div>
        </div>
        <ul className="space-y-2 text-sm">
          {(prog?.steps ?? (Object.keys(STEP_LABELS) as BuildStep[])).map((step, i) => {
            const state = i < current ? 'done' : i === current ? 'running' : 'pending'
            return (
              <li key={step} className={cn('flex items-center gap-2', state === 'pending' && 'text-muted-foreground')}>
                {state === 'done' ? (
                  <Check className="size-4 text-emerald-600" />
                ) : state === 'running' ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Circle className="size-4" />
                )}
                <span className="flex-1">{t(STEP_LABELS[step])}</span>
                {state === 'running' && prog!.total > 1 && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {t('build.count', { done: prog!.done, total: prog!.total })}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
        <div className="space-y-1 text-xs text-muted-foreground">
          {finished ? (
            <p>{t('build.finishing')}</p>
          ) : prog?.item ? (
            <p className="truncate">{t(ITEM_LABELS[prog.item.kind], { name: prog.item.name })}</p>
          ) : (
            prog?.message && <p className="truncate">{prog.message}</p>
          )}
          {cache && cache.reused + cache.made > 0 && (
            <p className="tabular-nums">{t('build.cacheCount', { reused: cache.reused, made: cache.made })}</p>
          )}
        </div>
        <div className="flex items-center gap-3 border-t pt-3">
          <p className="flex-1 text-xs text-muted-foreground">{finished ? null : stopping ? t('build.stopping') : t('build.stopHint')}</p>
          <Button variant="outline" size="sm" onClick={stop} disabled={stopping || !prog || finished}>
            {stopping ? <Loader2 className="animate-spin" /> : <Square />} {t('build.stop')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
