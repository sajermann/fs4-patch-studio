import type { Dated } from '@/api/types'
import { TableCell, TableHead } from '@/components/ui/table'
import { useI18n } from '@/i18n'

/** A project date (ISO 8601) in the interface language: day and time, short. */
export function useDateText() {
  const { lang } = useI18n()
  return (iso?: string | null) => {
    if (!iso) return ''
    const date = new Date(iso)
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(lang, { dateStyle: 'short', timeStyle: 'short' })
  }
}

/** "Created" and "Edited" headers of a list. */
export function DateHeads() {
  const { t } = useI18n()
  return (
    <>
      <TableHead>{t('dates.colCreated')}</TableHead>
      <TableHead>{t('dates.colUpdated')}</TableHead>
    </>
  )
}

/** The two date cells of a row; blank for an entry without dates (saved before they existed, or the game's own). */
export function DateCells({ entry }: { entry?: Dated }) {
  const text = useDateText()
  return (
    <>
      <TableCell className="whitespace-nowrap tabular-nums text-muted-foreground">{text(entry?.created_at)}</TableCell>
      <TableCell className="whitespace-nowrap tabular-nums text-muted-foreground">{text(entry?.updated_at)}</TableCell>
    </>
  )
}

/** "Created … · Edited …" under an entry's title; nothing when it has no dates. */
export function EntryDates({ entry }: { entry: Dated }) {
  const { t } = useI18n()
  const text = useDateText()
  const parts = [
    entry.created_at && t('dates.created', { date: text(entry.created_at) }),
    entry.updated_at && t('dates.updated', { date: text(entry.updated_at) }),
  ].filter(Boolean)
  if (!parts.length) return null
  return <p className="text-xs text-muted-foreground">{parts.join(' · ')}</p>
}
