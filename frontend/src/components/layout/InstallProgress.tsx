import { useQuery } from '@tanstack/react-query'
import { Check, Circle, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { InstallPhase } from '@/api/types'
import { useI18n, type MessageKey } from '@/i18n'
import { clock } from '@/lib/clock'
import { cn } from '@/lib/utils'

const POLL_MS = 400
const STEPS: Record<'install' | 'uninstall', InstallPhase[]> = {
  install: ['checking', 'restoring', 'copying', 'save'],
  uninstall: ['checking', 'restoring', 'save'],
}
const LABELS: Record<'install' | 'uninstall', Partial<Record<InstallPhase, MessageKey>>> = {
  install: {
    checking: 'install.stepChecking',
    restoring: 'install.stepRestoring',
    copying: 'install.stepCopying',
    save: 'install.stepSave',
  },
  uninstall: { checking: 'install.stepChecking', restoring: 'install.stepUninstalling', save: 'install.stepSave' },
}

const megabytes = (bytes: number, lang: string) =>
  (bytes / (1024 * 1024)).toLocaleString(lang, { maximumFractionDigits: bytes < 10 * 1024 * 1024 ? 1 : 0 })

/** Step by step progress of installing / uninstalling the patch in the game (GET /api/patch/install/progress), shown
 * inside the confirmation dialog while `active`: which step, which file, how much was copied. */
export function InstallProgress({ action, active }: { action: 'install' | 'uninstall'; active: boolean }) {
  const { t, lang } = useI18n()
  const [seen, setSeen] = useState(false) // this run answered at least once (the data is not the previous run's)
  const { data } = useQuery({
    queryKey: ['install-progress'],
    queryFn: api.installProgress,
    enabled: active,
    refetchInterval: active ? POLL_MS : false,
    gcTime: 0,
  })
  if (active && !seen && data?.running && data.action === action) setSeen(true)
  if (!active && seen) setSeen(false)
  if (!active) return null

  const prog = seen && data?.action === action ? data : undefined
  const steps = STEPS[action]
  const phase = prog?.phase === 'backup' ? 'checking' : prog?.phase
  const finished = !!prog && !prog.running
  const current = finished ? steps.length : phase ? steps.indexOf(phase) : 0
  const copying = prog?.phase === 'copying' || (prog?.phase === 'save' && action === 'install')
  const share = prog?.bytes_total ? prog.bytes_done / prog.bytes_total : prog?.total ? prog.done / prog.total : 0
  const overall = finished ? 100 : Math.round(((Math.max(current, 0) + (phase === 'save' ? 0 : share)) / steps.length) * 100)

  const detail = (() => {
    if (!prog) return t('install.starting')
    if (finished) return t('install.finishing')
    if (prog.phase === 'undoing') return t('install.undoing')
    if (prog.phase === 'backup') return t('install.backup', { name: prog.name ?? '' })
    if (prog.name) return prog.name
    return null
  })()

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="space-y-1.5">
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
          <span>{overall}%</span>
          <span>{prog?.elapsed !== undefined ? clock(prog.elapsed) : '0:00'}</span>
        </div>
      </div>
      <ul className="space-y-1.5 text-sm">
        {steps.map((step, i) => {
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
              <span className="flex-1">{t(LABELS[action][step]!)}</span>
              {state === 'running' && prog && prog.total > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {t('build.count', { done: prog.done, total: prog.total })}
                </span>
              )}
            </li>
          )
        })}
      </ul>
      <div className="space-y-1 text-xs text-muted-foreground">
        {detail && <p className={cn('truncate', detail === prog?.name && 'font-mono')}>{detail}</p>}
        {copying && prog && prog.bytes_total > 0 && (
          <p className="tabular-nums">
            {t('install.bytes', { done: megabytes(prog.bytes_done, lang), total: megabytes(prog.bytes_total, lang) })}
          </p>
        )}
      </div>
    </div>
  )
}
