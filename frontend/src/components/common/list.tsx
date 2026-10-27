import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react'
import { useLayoutEffect, useMemo, useRef, type ReactNode } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'
import { useReturning } from '@/lib/back'

export const ALL = 'all'
const PAGE_SIZES = [25, 50, 100]
const DEFAULT_PAGE_SIZE = 50

/** List filters kept in the URL (?q=…&league=…&page=…), so they survive opening an item and coming back.
 * Changing any filter goes back to page 1. */
export function useListParams<K extends string>(keys: readonly K[]) {
  const [params, setParams] = useSearchParams()
  const values = Object.fromEntries(keys.map((k) => [k, params.get(k) ?? (k === 'q' ? '' : ALL)])) as Record<K, string>
  const set = (key: K, value: string) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p)
        if (value === '' || value === ALL) next.delete(key)
        else next.set(key, value)
        next.delete('page')
        return next
      },
      { replace: true },
    )
  const page = Math.max(1, Number(params.get('page')) || 1)
  const pageSize = PAGE_SIZES.includes(Number(params.get('size'))) ? Number(params.get('size')) : DEFAULT_PAGE_SIZE
  const setPage = (n: number, size = pageSize) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p)
        if (n > 1) next.set('page', String(n))
        else next.delete('page')
        if (size !== DEFAULT_PAGE_SIZE) next.set('size', String(size))
        else next.delete('size')
        return next
      },
      { replace: true },
    )
  const active = keys.some((k) => values[k] !== '' && values[k] !== ALL)
  const clear = () => setParams(new URLSearchParams(), { replace: true })
  return { values, set, page, pageSize, setPage, active, clear }
}

/** The rows of the current page (the page number is clamped to the last page). */
export function usePage<T>(items: T[], page: number, pageSize: number) {
  return useMemo(() => {
    const pages = Math.max(1, Math.ceil(items.length / pageSize))
    const current = Math.min(page, pages)
    return { rows: items.slice((current - 1) * pageSize, current * pageSize), page: current, pages, total: items.length }
  }, [items, page, pageSize])
}

export const matches = (needle: string, ...texts: (string | null | undefined)[]) => {
  const n = needle.trim().toLowerCase()
  return !n || texts.some((t) => t?.toLowerCase().includes(n))
}

export function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="w-60 pl-8" />
    </div>
  )
}

export interface FilterOption {
  value: string
  label: string
  group?: string
}

/** Select of one filter; options with a `group` are listed under that heading. */
export function FilterSelect({
  value,
  onChange,
  options,
  className = 'w-48',
}: {
  value: string
  onChange: (v: string) => void
  options: FilterOption[]
  className?: string
}) {
  const groups = [...new Set(options.map((o) => o.group ?? ''))]
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {groups.map((g) => (
          <SelectGroup key={g}>
            {g && <SelectLabel>{g}</SelectLabel>}
            {options
              .filter((o) => (o.group ?? '') === g)
              .map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Filter bar: the filters + "Limpar" when any is set. */
export function FilterBar({ children, active, onClear }: { children: ReactNode; active: boolean; onClear: () => void }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-wrap items-center gap-2">
      {children}
      {active && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X /> {t('list.clearFilters')}
        </Button>
      )}
    </div>
  )
}

/** "1–50 de 1170" + page size + previous/next. */
export function Pager({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number
  pages: number
  total: number
  pageSize: number
  onPage: (page: number, size?: number) => void
}) {
  const { t } = useI18n()
  const first = total ? (page - 1) * pageSize + 1 : 0
  return (
    <div className="flex flex-wrap items-center justify-end gap-2 text-sm text-muted-foreground">
      <span className="tabular-nums">
        {t('list.range', { first, last: Math.min(page * pageSize, total), total })}
      </span>
      <Select value={String(pageSize)} onValueChange={(v) => onPage(1, Number(v))}>
        <SelectTrigger size="sm" className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PAGE_SIZES.map((n) => (
            <SelectItem key={n} value={String(n)}>
              {t('list.perPage', { count: n })}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={t('list.previousPage')}>
        <ChevronLeft />
      </Button>
      <span className="tabular-nums">
        {page}/{pages}
      </span>
      <Button variant="ghost" size="icon" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={t('list.nextPage')}>
        <ChevronRight />
      </Button>
    </div>
  )
}

/** Class of a list page's root: fills the height left on screen, so the table scrolls inside and the pager stays
 * visible. */
export const LIST_PAGE = 'flex h-full min-h-[24rem] flex-col gap-4'

const scrollTops = new Map<string, number>() // list URL (path + filters) → last vertical scroll

/** Table that fills the rest of the page and scrolls inside: vertical scroll moves only the rows (the header
 * sticks), horizontal scroll moves the header too. The column marked `data-grow` (its header and cells) takes the free width; the other
 * columns keep their content on one line (images keep their size: a shrunk column would squeeze them to 0). Coming back through an item's "←" restores the scroll the list had. */
export function ScrollTable({ children }: { children: ReactNode }) {
  const loc = useLocation()
  const key = loc.pathname + loc.search
  const returning = useReturning()
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    if (returning && ref.current) ref.current.scrollTop = scrollTops.get(key) ?? 0
  }, [key, returning])
  return (
    <div
      ref={ref}
      onScroll={(e) => scrollTops.set(key, e.currentTarget.scrollTop)}
      className="min-h-0 flex-1 overflow-auto rounded-md border"
    >
      <table
        className={
          'w-full caption-bottom text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap ' +
          '[&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 [&_thead]:bg-background [&_thead]:shadow-[inset_0_-1px_0_var(--border)] ' +
          '[&_[data-grow]]:w-full [&_[data-grow]]:whitespace-normal [&_td_img]:max-w-none'
        }
      >
        {children}
      </table>
    </div>
  )
}
