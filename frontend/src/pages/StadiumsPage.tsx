import { Lock, LockOpen } from 'lucide-react'
import {
  ALL,
  FilterBar,
  FilterSelect,
  LIST_PAGE,
  matches,
  Pager,
  ScrollTable,
  SearchInput,
  useListParams,
  usePage,
} from '@/components/common/list'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useOriginalChanges } from '@/lib/originals'
import { useOriginalStadiums } from '@/state/queries'

export function StadiumsPage() {
  const { t } = useI18n()
  const stadiums = useOriginalStadiums().data ?? []
  const { stadiumLocked, setStadiumLocked } = useOriginalChanges()
  const list = useListParams(['q', 'status'] as const)
  const f = list.values

  const rows = stadiums.filter((s) => {
    const locked = stadiumLocked(s)
    return (
      matches(f.q, s.name) &&
      (f.status === ALL ||
        (f.status === 'locked' && locked) ||
        (f.status === 'unlocked' && !locked) ||
        (f.status === 'changed' && locked !== s.locked))
    )
  })
  const page = usePage(rows, list.page, list.pageSize)

  return (
    <div className={LIST_PAGE}>
      <div>
        <h1 className="text-2xl font-semibold">{t('nav.stadiums')}</h1>
        <p className="text-sm text-muted-foreground">{t('stadiums.description')}</p>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('stadiums.search')} />
        <FilterSelect
          value={f.status}
          onChange={(v) => list.set('status', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.statusAll') },
            { value: 'locked', label: t('stadiums.statusLocked') },
            { value: 'unlocked', label: t('stadiums.statusUnlocked') },
            { value: 'changed', label: t('stadiums.statusChanged') },
          ]}
        />
      </FilterBar>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('list.colId')}</TableHead>
            <TableHead>{t('stadiums.colStatus')}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                {t('stadiums.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((s) => {
            const locked = stadiumLocked(s)
            return (
              <TableRow key={s.id}>
                <TableCell data-grow className="font-medium">
                  {s.name}
                </TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{s.id}</TableCell>
                <TableCell>
                  <Badge variant={locked ? 'outline' : 'secondary'} className="font-normal">
                    {locked ? t('stadiums.locked') : t('stadiums.unlocked')}
                  </Badge>
                  {locked !== s.locked && <span className="ml-2 text-xs text-muted-foreground">{t('stadiums.changed')}</span>}
                </TableCell>
                <TableCell>
                  <Button variant="outline" size="sm" onClick={() => setStadiumLocked(s, !locked)}>
                    {locked ? <LockOpen /> : <Lock />} {locked ? t('list.unlock') : t('list.lock')}
                  </Button>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </ScrollTable>
      <Pager page={page.page} pages={page.pages} total={page.total} pageSize={list.pageSize} onPage={list.setPage} />
    </div>
  )
}
