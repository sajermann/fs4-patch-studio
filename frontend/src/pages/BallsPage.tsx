import { ZipImportButton } from '@/components/common/share'
import { DateCells, DateHeads } from '@/components/common/dates'
import { Download, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Ball, OriginalBall } from '@/api/types'
import { BallThumb } from '@/components/common/BallThumb'
import { EntityIssues, OriginalBadge } from '@/components/common/form'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, matches, Pager, ScrollTable, SearchInput, useListParams, usePage } from '@/components/common/list'
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { admitImported, ballKey, ballName, ballPath, gameBallName, REGION_LABELS, stadiumsUsing, useBallSlots } from '@/lib/balls'
import { newUid, useProject, useSameAsGame } from '@/state/project'
import { useOriginalBalls, useOriginalStadiums } from '@/state/queries'

type Row = { kind: 'project'; ball: Ball } | { kind: 'original'; ball: OriginalBall }

const rowKey = (r: Row) => (r.kind === 'project' ? r.ball.uid : `game-${r.ball.id}`)

export function BallsPage() {
  const { t } = useI18n()
  const { draft, dirty, addBalls, updateBall, removeBalls, save } = useProject()
  const originalsQuery = useOriginalBalls()
  const originals = originalsQuery.data
  const stadiums = useOriginalStadiums().data ?? []
  const navigate = useNavigate()
  const from = useFrom(t('nav.balls'))
  const list = useListParams(['q', 'origin', 'status'] as const)
  const f = list.values
  const slots = useBallSlots()
  const sameAsGame = useSameAsGame()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [askAll, setAskAll] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)

  const gameName = (b: OriginalBall) => gameBallName(b, b.id, (id) => t('balls.gameName', { id }))
  const using = (b: Ball | { original_id: number }) => stadiumsUsing(draft, stadiums, b)

  // the game's balls edited in the project show once, as their entry; ones only opened list as the game's
  const mine = (draft.balls ?? []).filter((b) => !sameAsGame(b.uid))
  const edited = new Map(mine.filter((b) => b.original_id != null).map((b) => [b.original_id!, b]))
  const rows: Row[] = [
    ...mine.map((ball) => ({ kind: 'project' as const, ball })),
    ...(originals ?? []).filter((b) => !edited.has(b.id)).map((ball) => ({ kind: 'original' as const, ball })),
  ].filter((r) => {
    const name = r.kind === 'project' ? r.ball.name : gameName(r.ball)
    const credits = r.kind === 'project' ? r.ball.credits : 'EA'
    const id = r.kind === 'project' ? (r.ball.original_id ?? r.ball.code) : r.ball.id
    return (
      matches(f.q, name, credits, id != null ? String(id) : undefined) &&
      (f.origin === ALL || f.origin === r.kind) &&
      (f.status === ALL || (f.status === 'hidden') === (r.kind === 'project' && !!r.ball.hidden))
    )
  })
  const page = usePage(rows, list.page, list.pageSize)
  const selectable = (r: Row) => r.kind === 'project'
  const pageKeys = page.rows.filter(selectable).map(rowKey)
  const allKeys = rows.filter(selectable).map(rowKey)
  const allOnPage = pageKeys.length > 0 && pageKeys.every((k) => selected.has(k))
  const picked = mine.filter((b) => selected.has(b.uid))
  const toggle = (key: string) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const selectMany = (keys: string[]) => {
    setSelected((s) => new Set([...s, ...keys]))
    setAskAll(false)
  }

  const create = () => {
    if (!slots.free) {
      toast.error(t('balls.slotsFull', { total: slots.total }))
      return
    }
    const uid = newUid()
    addBalls([{ uid, name: '' }])
    navigate(ballPath(uid), from)
  }

  const download = async () => {
    const exportable = picked.filter((b) => b.original_id == null || (b.mesh && b.texture))
    if (exportable.length < picked.length) toast.warning(t('balls.downloadSkipsGame', { count: picked.length - exportable.length }))
    if (!exportable.length) return
    setBusy(true)
    try {
      if (dirty) await save()
      const { name, blob } = await api.exportBalls(
        exportable.map((b) => b.uid),
        exportable.length > 1,
      )
      saveBlob(name, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('balls.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const inUse = picked.map((b) => ({ ball: b, users: using(b) })).filter((u) => u.users.length && u.ball.original_id == null)
  const versionLabel = (region: number) => (REGION_LABELS[region] ? ` (${t(REGION_LABELS[region])})` : '')

  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.balls')}</h1>
          <p className="text-sm text-muted-foreground">{t('balls.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={slots.free ? 'secondary' : 'destructive'} className="font-normal" title={t('balls.slotsHint', { total: slots.total })}>
            {t('balls.slots', { used: slots.used, total: slots.total })}
          </Badge>
          <ZipImportButton
            kind="balls"
            read={async (file) => {
              const r = await api.importBalls(file)
              return { items: r.balls, problems: r.problems }
            }}
            // an entry it replaces gives its code back
            admit={(items, replaced) => admitImported(items as Ball[], slots.free + replaced.filter((b) => !(b as Ball).hidden && (b as Ball).original_id == null).length)}
            label={t('balls.importMany')}
            hint={t('balls.importManyHint')}
          />
          <Button onClick={create}>
            <Plus /> {t('balls.new')}
          </Button>
        </div>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('balls.search')} />
        <FilterSelect
          value={f.origin}
          onChange={(v) => list.set('origin', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.originAll') },
            { value: 'project', label: t('list.originProject') },
            { value: 'original', label: t('list.originOriginal') },
          ]}
        />
        <FilterSelect
          value={f.status}
          onChange={(v) => list.set('status', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.statusAll') },
            { value: 'visible', label: t('players.statusInPatch') },
            { value: 'hidden', label: t('teams.statusHidden') },
          ]}
        />
        <div className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" disabled={!picked.length || busy} onClick={() => void download()}>
            <Download /> {t('balls.downloadSelected', { count: picked.length })}
          </Button>
          <Button variant="outline" size="sm" disabled={!picked.length} onClick={() => setDeleting(true)}>
            <Trash2 /> {t('balls.deleteSelected', { count: picked.length })}
          </Button>
        </div>
      </FilterBar>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <Checkbox
                checked={allOnPage}
                disabled={!pageKeys.length}
                aria-label={t('balls.selectAll')}
                onCheckedChange={(v) => {
                  if (v === true) setAskAll(true)
                  else setSelected(new Set())
                }}
              />
            </TableHead>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('balls.colCredits')}</TableHead>
            <TableHead>{t('balls.colStadiums')}</TableHead>
            <TableHead>{t('balls.colId')}</TableHead>
            <DateHeads />
            <TableHead className="w-12" />
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                {originalsQuery.error
                  ? t('balls.originalsFailed', { error: originalsQuery.error.message })
                  : originals === undefined
                    ? t('common.loading')
                    : t('balls.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((r) => {
            if (r.kind === 'original') {
              const b = r.ball
              const users = using({ original_id: b.id }).length
              return (
                <TableRow key={rowKey(r)} className="cursor-pointer text-muted-foreground" title={t('balls.editOriginalHint')} onClick={() => navigate(ballPath(b.id), from)}>
                  <TableCell />
                  <TableCell data-grow>
                    <span className="flex items-center gap-2">
                      <BallThumb id={b.id} />
                      <span className="text-foreground">{gameName(b)}</span>
                      <OriginalBadge />
                    </span>
                  </TableCell>
                  <TableCell>EA</TableCell>
                  <TableCell className="tabular-nums" title={t('balls.stadiumsHint')}>
                    {users || '—'}
                  </TableCell>
                  <TableCell className="tabular-nums">{b.id}</TableCell>
                  <DateCells />
                  <TableCell />
                  <TableCell />
                </TableRow>
              )
            }
            const b = r.ball
            const original = b.original_id != null
            const users = using(original ? { original_id: b.original_id! } : b).length
            return (
              <TableRow key={rowKey(r)} className="cursor-pointer" onClick={() => navigate(ballPath(ballKey(b)), from)}>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox checked={selected.has(b.uid)} onCheckedChange={() => toggle(b.uid)} aria-label={t('balls.select')} />
                </TableCell>
                <TableCell data-grow className={b.hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                  <span className="flex items-center gap-2">
                    <BallThumb ball={b} />
                    {b.name.trim() || <span className="text-muted-foreground">{t('common.unnamed')}</span>}
                    {original && <OriginalBadge entry={b.uid} />}
                    {b.hidden && <OutOfPatchBadge />}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">{b.credits || '—'}</TableCell>
                <TableCell className="tabular-nums" title={t('balls.stadiumsHint')}>
                  {users || '—'}
                </TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{b.original_id ?? b.code ?? t('common.auto')}</TableCell>
                <DateCells entry={b} />
                <TableCell>
                  <EntityIssues uid={b.uid} />
                </TableCell>
                <TableCell>
                  <span className="flex items-center justify-end gap-1">
                    {!original && (
                      <HideButton
                        hidden={!!b.hidden}
                        onToggle={() => {
                          if (b.hidden && !slots.free) {
                            toast.error(t('balls.slotsFull', { total: slots.total }))
                            return
                          }
                          updateBall(b.uid, { hidden: !b.hidden })
                        }}
                        hideHint={t('balls.hideHint')}
                        showHint={t('balls.showHint')}
                      />
                    )}
                  </span>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </ScrollTable>
      <Pager page={page.page} pages={page.pages} total={page.total} pageSize={list.pageSize} onPage={list.setPage} />

      <AlertDialog open={askAll} onOpenChange={setAskAll}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('balls.selectAllTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('balls.selectAllDescription', { page: pageKeys.length, all: allKeys.length })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button variant="outline" onClick={() => selectMany(pageKeys)}>
              {t('balls.selectPage', { count: pageKeys.length })}
            </Button>
            <AlertDialogAction onClick={() => selectMany(allKeys)}>{t('balls.selectEvery', { count: allKeys.length })}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('balls.deleteTitle', { count: picked.length })}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                {inUse.length > 0 && <p>{t('balls.deleteUsedMany')}</p>}
                {inUse.length > 0 && (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {inUse.map(({ ball, users }) => (
                      <li key={ball.uid}>
                        <span className="font-medium text-foreground">{ballName(ball, t('common.unnamed'))}</span>:{' '}
                        {users.map((u) => u.stadium.name + versionLabel(u.version.region)).join(', ')}
                      </li>
                    ))}
                  </ul>
                )}
                <p>{t('balls.deleteDescription')}</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removeBalls(picked.map((b) => b.uid)) // also takes them off their stadiums
                setSelected(new Set())
              }}
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
