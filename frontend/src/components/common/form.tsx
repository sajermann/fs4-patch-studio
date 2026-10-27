import { AlertTriangle, ChevronLeft, ChevronRight, CircleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { originalCrestUrl } from '@/api/client'
import type { Issue, OriginalTeam, RGB } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useI18n } from '@/i18n'
import { issueText } from '@/lib/issues'
import { useIssues } from '@/state/project'
import { cn } from '@/lib/utils'

/** Validation messages of one entity field. */
export function FieldIssues({ issues }: { issues: Issue[] }) {
  const { t } = useI18n()
  if (!issues.length) return null
  return (
    <ul className="mt-1 space-y-0.5">
      {issues.map((i, k) => (
        <li
          key={k}
          className={cn(
            'flex items-start gap-1 text-xs',
            i.severity === 'error' ? 'text-destructive' : 'text-amber-600 dark:text-amber-500',
          )}
        >
          {i.severity === 'error' ? <CircleAlert className="mt-0.5 size-3 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3 shrink-0" />}
          {issueText(t, i)}
        </li>
      ))}
    </ul>
  )
}

/** Label + control + the validation messages of `entity.field`. */
export function Field({
  label,
  entity,
  field,
  hint,
  className,
  children,
}: {
  label: string
  entity?: string
  field?: string
  hint?: string
  className?: string
  children: ReactNode
}) {
  const issues = useIssues(entity, field)
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {field && <FieldIssues issues={issues} />}
    </div>
  )
}

export const toHex = (rgb: RGB) => '#' + rgb.map((v) => v.toString(16).padStart(2, '0')).join('')
export const fromHex = (hex: string): RGB => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as RGB

export function ColorInput({ value, onChange }: { value: RGB; onChange: (v: RGB) => void }) {
  const { t } = useI18n()
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={toHex(value)}
        onChange={(e) => onChange(fromHex(e.target.value))}
        className="h-9 w-12 cursor-pointer rounded-md border bg-transparent p-1"
        aria-label={t('form.pickColor')}
      />
      <Input
        value={toHex(value).toUpperCase()}
        onChange={(e) => /^#[0-9a-fA-F]{6}$/.test(e.target.value) && onChange(fromHex(e.target.value))}
        className="w-28 font-mono"
      />
    </div>
  )
}

/** Steps through a list of game codes. Shows only the position in the list (the raw code means nothing to the
 * user); when the value is unset it shows the position of the inherited value, marked "padrão". Fixed width (184px). */
export function Stepper({
  value,
  options,
  onChange,
  inherited,
}: {
  value: number | undefined
  options: number[]
  onChange: (v: number | undefined) => void
  inherited?: number | null
}) {
  const { t } = useI18n()
  const idx = value === undefined ? -1 : options.indexOf(value)
  const inheritedIdx = inherited === undefined || inherited === null ? -1 : options.indexOf(inherited)
  const go = (delta: number) => {
    if (!options.length) return
    const next = idx < 0 ? (delta > 0 ? 0 : options.length - 1) : (idx + delta + options.length) % options.length
    onChange(options[next])
  }
  return (
    <div className="flex items-center gap-1">
      <Button type="button" variant="outline" size="icon" onClick={() => go(-1)} aria-label={t('form.previous')}>
        <ChevronLeft />
      </Button>
      <div className="w-28 rounded-md border px-2 py-1.5 text-center text-sm whitespace-nowrap tabular-nums">
        {value !== undefined ? (
          <>
            {idx + 1}
            <span className="text-xs text-muted-foreground">/{options.length}</span>
          </>
        ) : inheritedIdx >= 0 ? (
          <span className="text-muted-foreground">
            {inheritedIdx + 1}
            <span className="text-xs">
              /{options.length} {t('common.default')}
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground">{t('common.default')}</span>
        )}
      </div>
      <Button type="button" variant="outline" size="icon" onClick={() => go(1)} aria-label={t('form.next')}>
        <ChevronRight />
      </Button>
    </div>
  )
}

export function OriginalBadge() {
  const { t } = useI18n()
  return (
    <Badge variant="secondary" className="font-normal">
      {t('common.original')}
    </Badge>
  )
}

/** Error/warning counters for one entity, shown in tables. */
export function EntityIssues({ uid }: { uid: string }) {
  const issues = useIssues(uid)
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  return (
    <span className="inline-flex gap-2 text-xs">
      {errors > 0 && (
        <span className="inline-flex items-center gap-1 text-destructive">
          <CircleAlert className="size-3" /> {errors}
        </span>
      )}
      {warnings > 0 && (
        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-500">
          <AlertTriangle className="size-3" /> {warnings}
        </span>
      )}
    </span>
  )
}

/** Menu crest of an original team (read from the originals); its two colors when the game has none. */
export function OriginalCrest({ team, className }: { team: OriginalTeam; className?: string }) {
  return team.crest ? (
    <img src={originalCrestUrl(team.id)} alt="" loading="lazy" className={cn('size-8 object-contain', className)} />
  ) : (
    <span className="flex gap-0.5">
      <Swatch rgb={team.primary_color} />
      <Swatch rgb={team.secondary_color} />
    </span>
  )
}

export function Swatch({ rgb, className }: { rgb: RGB; className?: string }) {
  return <span className={cn('inline-block size-4 rounded-sm border', className)} style={{ background: toHex(rgb) }} />
}

/** Optional number input: empty string = undefined. */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  placeholder,
  className,
}: {
  value: number | undefined
  onChange: (v: number | undefined) => void
  min?: number
  max?: number
  placeholder?: string
  className?: string
}) {
  return (
    <Input
      type="number"
      value={value ?? ''}
      min={min}
      max={max}
      placeholder={placeholder}
      className={className}
      onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
    />
  )
}
