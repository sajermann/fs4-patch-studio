import { AlertTriangle, ChevronLeft, ChevronRight, CircleAlert, CircleHelp } from 'lucide-react'
import type { ReactNode } from 'react'
import { imageUrl, originalCrestUrl } from '@/api/client'
import type { Issue, OriginalTeam, RGB, Team } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { issueText } from '@/lib/issues'
import { useIssues, useWasEdited } from '@/state/project'
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
  help,
  className,
  children,
}: {
  label: ReactNode
  entity?: string
  field?: string
  hint?: string
  /** shown in a tooltip on a (?) icon next to the label */
  help?: ReactNode
  className?: string
  children: ReactNode
}) {
  const issues = useIssues(entity, field)
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label>
        {label}
        {help && (
          <Tooltip>
            <TooltipTrigger asChild>
              <CircleHelp className="size-3.5 shrink-0 cursor-help text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{help}</TooltipContent>
          </Tooltip>
        )}
      </Label>
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
/** "<position>/<total>" of a value in its options; the inherited one is muted and says "default". */
/** label: the option's name instead of its position in the list ("n/total"). */
export function OptionCount({ value, options, inherited, label }: {
  value: number | undefined
  options: number[]
  inherited?: number | null
  label?: (option: number) => string
}) {
  const { t } = useI18n()
  const idx = value === undefined ? -1 : options.indexOf(value)
  const inheritedIdx = inherited === undefined || inherited === null ? -1 : options.indexOf(inherited)
  if (label) {
    if (idx >= 0) return <span>{label(options[idx])}</span>
    if (inheritedIdx >= 0) return <span className="text-muted-foreground">{label(options[inheritedIdx])} <span className="text-xs">{t('common.default')}</span></span>
    return <span className="text-muted-foreground">{t('common.default')}</span>
  }
  if (value !== undefined) {
    return (
      <span className="tabular-nums">
        {idx + 1}
        <span className="text-xs text-muted-foreground">/{options.length}</span>
      </span>
    )
  }
  if (inheritedIdx >= 0) {
    return (
      <span className="text-muted-foreground tabular-nums">
        {inheritedIdx + 1}
        <span className="text-xs">
          /{options.length} {t('common.default')}
        </span>
      </span>
    )
  }
  return <span className="text-muted-foreground">{t('common.default')}</span>
}

export function Stepper({
  value,
  options,
  onChange,
  inherited,
  label,
  wide,
}: {
  value: number | undefined
  options: number[]
  onChange: (v: number | undefined) => void
  inherited?: number | null
  label?: (option: number) => string
  wide?: boolean // the middle takes the free width (long labels)
}) {
  const { t } = useI18n()
  const idx = value === undefined ? -1 : options.indexOf(value)
  const inheritedIdx = inherited === undefined || inherited === null ? -1 : options.indexOf(inherited)
  const go = (delta: number) => {
    if (!options.length) return
    const from = idx >= 0 ? idx : inheritedIdx // on a default value, the next one after it
    const next = from < 0 ? (delta > 0 ? 0 : options.length - 1) : (from + delta + options.length) % options.length
    onChange(options[next])
  }
  return (
    <div className="flex items-center gap-1">
      <Button type="button" variant="outline" size="icon" onClick={() => go(-1)} aria-label={t('form.previous')}>
        <ChevronLeft />
      </Button>
      <div className={cn('min-w-0 shrink rounded-md border px-2 py-1.5 text-center text-sm whitespace-nowrap', wide ? 'flex-1 truncate' : 'w-28')}>
        <OptionCount value={value} options={options} inherited={inherited} label={label} />
      </div>
      <Button type="button" variant="outline" size="icon" onClick={() => go(1)} aria-label={t('form.next')}>
        <ChevronRight />
      </Button>
    </div>
  )
}

/** "original", or "era original" for an entry that edits one of the game's teams/players (entry = its uid; an entry
 * opened without changing anything still reads "original") and for a game team whose squad the project changes
 * (team = its teamid, with or without an entry) or a game league whose teams the project changes (league). */
export function OriginalBadge({ entry, team, league }: { entry?: string; team?: number | null; league?: number | null }) {
  const { t } = useI18n()
  const edited = useWasEdited(entry, team, league)
  return (
    <Badge variant="secondary" className="font-normal" title={edited ? t('common.wasOriginalHint') : undefined}>
      {edited ? t('common.wasOriginal') : t('common.original')}
    </Badge>
  )
}

/** Error/warning counters for one entity, shown in tables; hovering them lists the messages. */
export function EntityIssues({ uid }: { uid: string }) {
  const issues = useIssues(uid)
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  if (!issues.length) return null
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help gap-2 text-xs">
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
      </TooltipTrigger>
      <TooltipContent className="max-w-sm">
        <IssueList issues={issues} />
      </TooltipContent>
    </Tooltip>
  )
}

/** The messages of a list of issues, errors first, each with its icon (the tooltip of the counters). */
function IssueList({ issues }: { issues: Issue[] }) {
  const { t } = useI18n()
  const sorted = [...issues].sort((a, b) => (a.severity === 'error' ? 0 : 1) - (b.severity === 'error' ? 0 : 1))
  return (
    <ul className="space-y-1">
      {sorted.map((i, k) => (
        <li key={k} className="flex items-start gap-1.5">
          {i.severity === 'error' ? (
            <CircleAlert className="mt-0.5 size-3 shrink-0 text-red-400 dark:text-red-600" />
          ) : (
            <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-400 dark:text-amber-600" />
          )}
          <span>{issueText(t, i)}</span>
        </li>
      ))}
    </ul>
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

/** A project team's crest, or its two colors when it has none. */
export function TeamCrest({ team, className }: { team: Team; className?: string }) {
  return team.crest ? (
    <img src={imageUrl(team.crest)} alt="" className={cn('size-8 object-contain', className)} />
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
