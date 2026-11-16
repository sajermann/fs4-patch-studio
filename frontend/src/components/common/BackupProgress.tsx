import { Check, Circle, Loader2 } from 'lucide-react'
import type { BackupPhase, BackupProgress as Progress } from '@/api/types'
import { useI18n, type MessageKey } from '@/i18n'
import { clock } from '@/lib/clock'
import { cn } from '@/lib/utils'

const STEPS: Record<'export' | 'restore', BackupPhase[]> = {
  export: ['zipping'],
  restore: ['uploading', 'checking', 'extracting', 'finishing'],
}
const LABELS: Record<BackupPhase, MessageKey> = {
  zipping: 'backup.stepZipping',
  uploading: 'backup.stepUploading',
  checking: 'backup.stepChecking',
  extracting: 'backup.stepExtracting',
  finishing: 'backup.stepFinishing',
}

const megabytes = (bytes: number, lang: string) =>
  (bytes / (1024 * 1024)).toLocaleString(lang, { maximumFractionDigits: bytes < 10 * 1024 * 1024 ? 1 : 0 })

/** Step by step progress of a backup download ('export': the zip being written) or restore (the upload, measured by
 * the screen, then the backend's steps): bar, clock, the current file, files and MB done. `prog` = the backend's
 * progress of this run (undefined until it answers). */
export function BackupProgress({ action, prog }: { action: 'export' | 'restore'; prog?: Progress }) {
  const { t, lang } = useI18n()
  const steps = STEPS[action]
  const finished = !!prog && !prog.running && prog.phase !== 'uploading'
  const current = finished ? steps.length : prog?.phase ? steps.indexOf(prog.phase) : 0
  const share = prog?.bytes_total ? prog.bytes_done / prog.bytes_total : prog?.total ? prog.done / prog.total : 0
  const counted = prog?.phase === 'uploading' || prog?.phase === 'zipping' || prog?.phase === 'extracting'
  const overall = finished ? 100 : Math.round(((Math.max(current, 0) + (counted ? share : 0)) / steps.length) * 100)
  const detail = !prog ? t('backup.starting') : prog.name || null

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="space-y-1.5">
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
          <span>{overall}%</span>
          <span>{clock(prog?.elapsed ?? 0)}</span>
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
              <span className="flex-1">{t(LABELS[step])}</span>
              {state === 'running' && prog && prog.phase !== 'uploading' && prog.total > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">{t('build.count', { done: prog.done, total: prog.total })}</span>
              )}
            </li>
          )
        })}
      </ul>
      <div className="space-y-1 text-xs text-muted-foreground">
        {detail && <p className={cn('truncate', detail === prog?.name && 'font-mono')}>{detail}</p>}
        {counted && prog && prog.bytes_total > 0 && (
          <p className="tabular-nums">
            {t('backup.bytes', { done: megabytes(prog.bytes_done, lang), total: megabytes(prog.bytes_total, lang) })}
          </p>
        )}
      </div>
    </div>
  )
}
