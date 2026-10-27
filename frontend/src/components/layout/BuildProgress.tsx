import { useQuery } from '@tanstack/react-query'
import { Check, Circle, Loader2 } from 'lucide-react'
import { api } from '@/api/client'
import type { BuildStep } from '@/api/types'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n, type MessageKey } from '@/i18n'
import { cn } from '@/lib/utils'

const STEP_LABELS: Record<BuildStep, MessageKey> = {
  database: 'build.stepDatabase',
  leagues: 'build.stepLeagues',
  teams: 'build.stepTeams',
  images: 'build.stepImages',
  texts: 'build.stepTexts',
  files: 'build.stepFiles',
}
const POLL_MS = 500

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

/** Step by step progress of "Gerar patch", polled from the backend while `open` (it cannot be closed meanwhile). */
export function BuildProgressDialog({ open }: { open: boolean }) {
  const { t } = useI18n()
  const { data } = useQuery({
    queryKey: ['patch-progress'],
    queryFn: api.buildProgress,
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
    gcTime: 0,
  })
  // until the first answer of this build arrives, show it starting (not the previous build)
  const prog = data?.running ? data : undefined
  const current = prog?.step ? prog.steps.indexOf(prog.step) : -1
  const stepShare = prog?.total ? prog.done / prog.total : 0
  const overall = prog ? Math.round(((Math.max(current, 0) + stepShare) / prog.steps.length) * 100) : 0

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
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
        {prog?.message && <p className="truncate text-xs text-muted-foreground">{prog.message}</p>}
      </DialogContent>
    </Dialog>
  )
}
