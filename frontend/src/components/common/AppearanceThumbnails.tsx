import { ArrowLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { appearanceThumbUrl } from '@/api/client'
import { OptionCount } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

/** Appearance codes the game has ready pictures of (fsmod.appearance_thumbs). */
export const THUMBNAIL_CODES = ['hairtypecode', 'haircolorcode', 'skintonecode', 'facialhairtypecode', 'facialhaircolorcode', 'eyecolorcode', 'eyebrowcode']

const ALL = 'all'

/** The game's picture of a code; its position in the list when the game has none (a few hairs). */
function Thumb({ code, value, variant, fallback, className }: {
  code: string
  value: number
  variant: number
  fallback: number
  className?: string
}) {
  const url = appearanceThumbUrl(code, value, variant)
  const [failed, setFailed] = useState<string | null>(null)
  if (failed === url) {
    return <span className={cn('flex items-center justify-center bg-muted text-xs text-muted-foreground tabular-nums', className)}>{fallback}</span>
  }
  return <img src={url} alt="" loading="lazy" className={cn('bg-muted object-cover', className)} onError={() => setFailed(url)} />
}

/** Field of the Visual card: shows the current picture and opens the pictures (they take the place of the card). */
export function ThumbnailField({ code, value, inherited, options, variant, onOpen }: {
  code: string
  value: number | undefined
  inherited?: number | null
  options: number[]
  variant: number
  onOpen: () => void
}) {
  const shown = value ?? inherited ?? undefined
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex h-9 w-full items-center gap-2 rounded-md border pr-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
    >
      {shown !== undefined && (
        <Thumb code={code} value={shown} variant={variant} fallback={options.indexOf(shown) + 1} className="size-[2.125rem] shrink-0 rounded-l-md" />
      )}
      <span className="min-w-0 flex-1 text-center whitespace-nowrap">
        <OptionCount value={value} options={options} inherited={inherited} />
      </span>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

/** The pictures of a code, in place of the Visual card: a click shows it in the preview beside it, Apply keeps it. */
export function ThumbnailPicker({ code, title, options, groups, value, variant, changed, onSelect, onApply, onCancel }: {
  code: string
  title: string
  options: number[]
  groups?: { key: string; label: string; codes: number[] }[] // opens on the group of the current value
  value: number | undefined
  variant: number
  changed: boolean
  onSelect: (value: number) => void
  onApply: () => void
  onCancel: () => void
}) {
  const { t } = useI18n()
  const selected = useRef<HTMLButtonElement>(null)
  const [group, setGroup] = useState(() => groups?.find((g) => value !== undefined && g.codes.includes(value))?.key ?? ALL)
  const shown = groups?.find((g) => g.key === group)?.codes
  useEffect(() => {
    selected.current?.scrollIntoView({ block: 'nearest' })
  }, [])
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <CardHeader>
        <div>
          <Button variant="ghost" size="sm" className="-ml-2" onClick={onCancel}>
            <ArrowLeft /> {t('playerEdit.pickBack')}
          </Button>
        </div>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{t('playerEdit.pickHint')}</CardDescription>
        {groups && (
          <div className="flex flex-wrap gap-1 pt-1">
            {[{ key: ALL, label: t('playerEdit.pickAll') }, ...groups].map((g) => (
              <button
                key={g.key}
                type="button"
                aria-pressed={g.key === group}
                onClick={() => setGroup(g.key)}
                className={cn(
                  'rounded-md border px-2 py-1 text-xs transition-colors',
                  g.key === group ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {g.label}
              </button>
            ))}
          </div>
        )}
      </CardHeader>
      <CardContent className="mx-3 grid max-h-[60vh] min-h-0 flex-1 auto-rows-max grid-cols-4 content-start gap-2 overflow-y-auto p-1 xl:max-h-none">
        {options.map((option, index) => (!shown || shown.includes(option)) && (
          <button
            key={option}
            ref={option === value ? selected : undefined}
            type="button"
            aria-pressed={option === value}
            aria-label={`${title} ${index + 1}`}
            onClick={() => onSelect(option)}
            className={cn(
              'overflow-hidden rounded-md border transition-colors hover:border-foreground/50',
              option === value && 'border-primary ring-2 ring-primary',
            )}
          >
            <Thumb code={code} value={option} variant={variant} fallback={index + 1} className="aspect-square w-full" />
            <span className="block py-0.5 text-center text-xs text-muted-foreground tabular-nums">{index + 1}</span>
          </button>
        ))}
      </CardContent>
      <CardContent className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button size="sm" disabled={!changed} onClick={onApply}>
          {t('common.apply')}
        </Button>
      </CardContent>
    </div>
  )
}
