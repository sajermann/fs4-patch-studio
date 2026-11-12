import { Check, Loader2, Mail, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { AppNotification, NotificationKind, NotificationReadState, NotificationSelection } from '@/api/types'
import { useDateText } from '@/components/common/dates'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, Pager, ScrollTable, useListParams } from '@/components/common/list'
import { DeleteNotificationsDialog, KindIcon, NotificationDialog, useNotificationActions } from '@/components/common/notifications'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useNotificationPage } from '@/state/queries'

const KINDS: NotificationKind[] = ['error', 'warning', 'success', 'info']
const STATES = ['unread', 'read'] as const satisfies NotificationReadState[]

/** What is selected: some ids, or every notification matching the filters except some (on every page; the backend
 * resolves it, so the list never has to be loaded whole). */
type Picked = { all: false; ids: Set<number> } | { all: true; exclude: Set<number> }
const NONE: Picked = { all: false, ids: new Set() }

export function NotificationsPage() {
  const { t } = useI18n()
  const date = useDateText()
  const list = useListParams(['kind', 'state'] as const)
  const kind = list.values.kind === ALL ? undefined : (list.values.kind as NotificationKind)
  const state = list.values.state === ALL ? undefined : (list.values.state as NotificationReadState)
  const query = useNotificationPage({ offset: (list.page - 1) * list.pageSize, limit: list.pageSize, kind, state })
  const data = query.data
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / list.pageSize))
  const rows = data?.items ?? []
  const actions = useNotificationActions()
  const [picked, setPicked] = useState<Picked>(NONE)
  const [askAll, setAskAll] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [shown, setShown] = useState<AppNotification | null>(null)

  // a page past the end (the last ones were deleted, or an old link): go to the last one
  const { page, setPage } = list
  useEffect(() => {
    if (data && page > pages) setPage(pages)
  }, [data, page, pages, setPage])
  // other filters = another set of notifications: the selection starts over
  const setFilter = (key: 'kind' | 'state', value: string) => {
    setPicked(NONE)
    list.set(key, value)
  }

  const isPicked = (id: number) => (picked.all ? !picked.exclude.has(id) : picked.ids.has(id))
  const count = picked.all ? Math.max(0, total - picked.exclude.size) : picked.ids.size
  const pageIds = rows.map((n) => n.id)
  const allOnPage = pageIds.length > 0 && pageIds.every(isPicked)
  const toggle = (id: number) =>
    setPicked((p) => {
      const set = new Set(p.all ? p.exclude : p.ids)
      if (set.has(id)) set.delete(id)
      else set.add(id)
      return p.all ? { all: true, exclude: set } : { all: false, ids: set }
    })
  const selection = (): NotificationSelection =>
    picked.all ? { all: true, kind, state, exclude: [...picked.exclude] } : { ids: [...picked.ids] }

  const after = (ok: boolean) => ok && setPicked(NONE)

  return (
    <div className={LIST_PAGE}>
      <div>
        <h1 className="text-2xl font-semibold">{t('notifications.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('notifications.description')}</p>
      </div>

      {/* filters (with "clear filters" next to them) on the left, the selection actions on the right */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FilterBar
          active={list.active}
          onClear={() => {
            setPicked(NONE)
            list.clear()
          }}
        >
          <FilterSelect
            value={list.values.kind}
            onChange={(v) => setFilter('kind', v)}
            options={[{ value: ALL, label: t('notifications.kindAll') }, ...KINDS.map((k) => ({ value: k, label: t(`notifications.kind.${k}`) }))]}
          />
          <FilterSelect
            value={list.values.state}
            onChange={(v) => setFilter('state', v)}
            options={[
              { value: ALL, label: t('notifications.stateAll') },
              ...STATES.map((s) => ({ value: s, label: t(`notifications.state.${s}`) })),
            ]}
          />
        </FilterBar>
        <div className="flex flex-wrap items-center gap-2">
          {count > 0 && (
            <>
              <span className="text-sm text-muted-foreground tabular-nums">{t('notifications.selected', { count })}</span>
              <Button variant="ghost" size="sm" onClick={() => setPicked(NONE)}>
                <X /> {t('notifications.clearSelection')}
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" disabled={!count || actions.busy} onClick={async () => after(await actions.mark(selection(), true))}>
            <Check /> {t('notifications.markReadSelected', { count })}
          </Button>
          <Button variant="outline" size="sm" disabled={!count || actions.busy} onClick={async () => after(await actions.mark(selection(), false))}>
            <Mail /> {t('notifications.markUnreadSelected', { count })}
          </Button>
          <Button variant="outline" size="sm" disabled={!count || actions.busy} onClick={() => setDeleting(true)}>
            <Trash2 /> {t('notifications.deleteSelected', { count })}
          </Button>
        </div>
      </div>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <Checkbox
                checked={allOnPage}
                disabled={!pageIds.length}
                aria-label={t('notifications.selectAll')}
                onCheckedChange={(v) => {
                  if (v !== true) setPicked(NONE)
                  else if (total > pageIds.length) setAskAll(true)
                  else setPicked({ all: false, ids: new Set(pageIds) })
                }}
              />
            </TableHead>
            <TableHead className="w-8" />
            <TableHead data-grow>{t('notifications.colMessage')}</TableHead>
            <TableHead>{t('notifications.colDate')}</TableHead>
            <TableHead className="w-8" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                {query.isLoading ? (
                  <Loader2 className="inline animate-spin" />
                ) : query.error ? (
                  t('notifications.loadFailed')
                ) : list.active ? (
                  t('notifications.noneFiltered')
                ) : (
                  t('notifications.none')
                )}
              </TableCell>
            </TableRow>
          )}
          {rows.map((n) => (
            <TableRow key={n.id} className="cursor-pointer" onClick={() => setShown(n)} data-state={isPicked(n.id) ? 'selected' : undefined}>
              <TableCell onClick={(e) => e.stopPropagation()}>
                <Checkbox checked={isPicked(n.id)} onCheckedChange={() => toggle(n.id)} aria-label={t('notifications.select')} />
              </TableCell>
              <TableCell title={t(`notifications.kind.${n.kind}`)}>
                <KindIcon kind={n.kind} />
              </TableCell>
              {/* max-w-0: the message takes the free width and is cut with "…" instead of widening the table */}
              <TableCell data-grow className="max-w-0">
                <p className={cn('truncate', !n.read && 'font-semibold')}>{n.title}</p>
                {n.description && <p className="truncate text-xs text-muted-foreground">{n.description}</p>}
              </TableCell>
              <TableCell className="text-muted-foreground tabular-nums">{date(n.created_at)}</TableCell>
              <TableCell title={n.read ? t('notifications.state.read') : t('notifications.state.unread')}>
                {!n.read && <span className="inline-block size-2 rounded-full bg-sky-500" />}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScrollTable>

      <Pager page={Math.min(list.page, pages)} pages={pages} total={total} pageSize={list.pageSize} onPage={list.setPage} />

      <AlertDialog open={askAll} onOpenChange={setAskAll}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('notifications.selectAllTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('notifications.selectAllDescription', { page: pageIds.length, all: total })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button
              variant="outline"
              onClick={() => {
                setPicked({ all: false, ids: new Set(pageIds) })
                setAskAll(false)
              }}
            >
              {t('notifications.selectPage', { count: pageIds.length })}
            </Button>
            <AlertDialogAction onClick={() => setPicked({ all: true, exclude: new Set() })}>
              {t('notifications.selectEvery', { count: total })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <DeleteNotificationsDialog
        open={deleting}
        onOpenChange={setDeleting}
        count={count}
        busy={actions.busy}
        onConfirm={async () => {
          const ok = await actions.remove(selection())
          after(ok)
          if (ok) setDeleting(false)
        }}
      />
      <NotificationDialog notification={shown} onClose={() => setShown(null)} />
    </div>
  )
}
