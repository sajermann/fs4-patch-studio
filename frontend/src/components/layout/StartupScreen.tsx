import { useQuery } from '@tanstack/react-query'
import { Check, Circle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { StartupActivity, StartupTask } from '@/api/types'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { clock } from '@/lib/clock'
import { cn } from '@/lib/utils'

export type StartupStepState = 'pending' | 'running' | 'done'
type TaskName = keyof StartupActivity['tasks']

/** One step of the opening: its text, where it is, and the backend task that says what it is doing. */
export interface StartupStep {
  label: MessageKey
  state: StartupStepState
  task: TaskName
}

const POLL_MS = 700
const SILENT_AFTER_S = 4 // without an answer for this long, say the app is not responding

// the moment the page started: the clock counts the whole opening, not only this screen
const OPENED_AT = Date.now()

/** What the app is loading while it opens, step by step, with what the backend is doing right now (GET
 * /api/startup), a clock and whether the backend still answers: the user sees it working instead of a bare
 * "loading" and does not close it thinking it froze. page: full window (before the app shell exists). */
export function StartupScreen({ steps, page = false }: { steps: StartupStep[]; page?: boolean }) {
  const { t, lang } = useI18n()
  const [now, setNow] = useState(OPENED_AT) // updated by a timer: render itself reads no time
  // dataUpdatedAt = the backend's last answer (a failed poll keeps it; the log skips repeats, no toast)
  const { data, dataUpdatedAt } = useQuery({
    queryKey: ['startup'],
    queryFn: api.startup,
    refetchInterval: POLL_MS,
    retry: false,
    gcTime: 0,
    meta: { errorShown: true },
  })
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [])
  const silent = Math.max(0, Math.floor((now - dataUpdatedAt) / 1000))

  const phaseText = (name: TaskName, task: StartupTask | undefined) => {
    if (!task?.phase) return null
    const key = `startup.phase.${name}.${task.phase}`
    // numbers as the language writes them (5.965 jogadores / 5,965 players)
    const params = Object.fromEntries(
      Object.entries(task.params).map(([k, v]) => [k, typeof v === 'number' ? v.toLocaleString(lang) : v]),
    )
    return hasMessage(key) ? t(key, params) : null
  }

  return (
    <div
      className={cn(
        'flex w-full justify-center',
        page ? 'min-h-svh items-center bg-background p-4' : 'items-start pt-[10vh]',
      )}
    >
      <div className="w-full max-w-xl space-y-5">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold">{t('startup.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('startup.subtitle')}</p>
        </div>
        <ul className="space-y-3 text-sm">
          {steps.map((step) => {
            const task = data?.tasks[step.task]
            const detail =
              step.state === 'running'
                ? (phaseText(step.task, task) ??
                  (task ? null : t(dataUpdatedAt ? 'startup.receiving' : 'startup.serverStarting')))
                : step.state === 'pending'
                  ? t('startup.waiting')
                  : null
            return (
              <li key={step.label} className="flex items-start gap-2.5">
                <span className="mt-0.5">
                  {step.state === 'done' ? (
                    <Check className="size-4 text-emerald-600" />
                  ) : step.state === 'running' ? (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  ) : (
                    <Circle className="size-4 text-muted-foreground" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className={cn('flex-1', step.state === 'pending' && 'text-muted-foreground')}>{t(step.label)}</span>
                    {step.state === 'running' && task && (
                      <span className="text-xs text-muted-foreground tabular-nums">{clock(task.elapsed)}</span>
                    )}
                  </div>
                  {detail && <p className="truncate text-xs text-muted-foreground">{detail}</p>}
                </div>
              </li>
            )
          })}
        </ul>
        <div className="flex items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
          {/* before the first answer the server is still starting: that is not "not responding" */}
          <span className="flex items-center gap-2">
            <span
              className={cn(
                'size-2 rounded-full',
                !dataUpdatedAt
                  ? 'bg-muted-foreground animate-pulse'
                  : silent >= SILENT_AFTER_S
                    ? 'bg-amber-500'
                    : 'bg-emerald-500 animate-pulse',
              )}
            />
            {!dataUpdatedAt
              ? t('startup.serverStarting')
              : silent >= SILENT_AFTER_S
                ? t('startup.notResponding', { seconds: silent })
                : t('startup.alive')}
          </span>
          <span className="tabular-nums">{clock((now - OPENED_AT) / 1000)}</span>
        </div>
      </div>
    </div>
  )
}
