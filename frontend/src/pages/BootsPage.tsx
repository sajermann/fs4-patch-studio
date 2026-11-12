import { ZipImportButton } from '@/components/common/share'
import { DateCells, DateHeads } from '@/components/common/dates'
import { Download, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Boot, OriginalBoot } from '@/api/types'
import { BootThumb } from '@/components/common/BootThumb'
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
import { admitImported, bootKey, bootName, bootPath, SURFACE_LABELS, useStreetSlots, wearers } from '@/lib/boots'
import { playerName } from '@/lib/players'
import { newUid, useProject, useSameAsGame } from '@/state/project'
import { useOriginalBoots } from '@/state/queries'

type Row = { kind: 'project'; boot: Boot } | { kind: 'original'; boot: OriginalBoot }

const rowKey = (r: Row) => (r.kind === 'project' ? r.boot.uid : `game-${r.boot.code}`)

export function BootsPage() {
  const { t } = useI18n()
  const { draft, dirty, addBoots, updateBoot, removeBoots, save } = useProject()
  const originalsQuery = useOriginalBoots()
  const originals = originalsQuery.data
  const navigate = useNavigate()
  const from = useFrom(t('nav.boots'))
  const list = useListParams(['q', 'origin', 'street', 'status'] as const)
  const f = list.values
  const slots = useStreetSlots()
  const sameAsGame = useSameAsGame()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [askAll, setAskAll] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)

  // the game's boots edited in the project show once, as their entry; ones only opened list as the game's
  const mine = (draft.boots ?? []).filter((b) => !sameAsGame(b.uid))
  const edited = new Map(mine.filter((b) => b.original_id != null).map((b) => [b.original_id!, b]))
  const rows: Row[] = [
    ...mine.map((boot) => ({ kind: 'project' as const, boot })),
    ...(originals ?? []).filter((b) => !edited.has(b.code)).map((boot) => ({ kind: 'original' as const, boot })),
  ].filter((r) => {
    const street = r.kind === 'project' ? (r.boot.original_id != null ? r.boot.original_id >= 500 && r.boot.original_id <= 619 : !!r.boot.street) : r.boot.street
    const name = r.kind === 'project' ? r.boot.name : `Original ${r.boot.code}`
    const credits = r.kind === 'project' ? r.boot.credits : 'EA'
    const code = r.kind === 'project' ? (r.boot.original_id ?? r.boot.code) : r.boot.code
    return (
      matches(f.q, name, credits, code != null ? String(code) : undefined) &&
      (f.origin === ALL || f.origin === r.kind) &&
      (f.street === ALL || (f.street === 'yes') === street) &&
      (f.status === ALL || (f.status === 'hidden') === (r.kind === 'project' && !!r.boot.hidden))
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
    const uid = newUid()
    addBoots([{ uid, name: '' }])
    navigate(bootPath(uid), from)
  }

  const download = async () => {
    const exportable = picked.filter((b) => b.original_id == null || (b.mesh && b.texture))
    if (exportable.length < picked.length) toast.warning(t('boots.downloadSkipsGame', { count: picked.length - exportable.length }))
    if (!exportable.length) return
    setBusy(true)
    try {
      if (dirty) await save()
      const { name, blob } = await api.exportBoots(
        exportable.map((b) => b.uid),
        exportable.length > 1,
      )
      saveBlob(name, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('boots.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const inUse = picked.map((b) => ({ boot: b, users: wearers(draft, b) })).filter((u) => u.users.length && u.boot.original_id == null)

  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.boots')}</h1>
          <p className="text-sm text-muted-foreground">{t('boots.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={slots.free ? 'secondary' : 'destructive'} className="font-normal" title={t('boots.streetSlotsHint')}>
            {t('boots.streetSlots', { used: slots.used, total: slots.total })}
          </Badge>
          <ZipImportButton
            kind="boots"
            read={async (file) => {
              const r = await api.importBoots(file)
              return { items: r.boots, problems: r.problems }
            }}
            // an entry it replaces gives its code back
            admit={(items, replaced) => admitImported(items as Boot[], slots.free + replaced.filter((b) => !!(b as Boot).street && !(b as Boot).hidden && (b as Boot).original_id == null).length)}
            label={t('boots.importMany')}
            hint={t('boots.importManyHint')}
          />
          <Button onClick={create}>
            <Plus /> {t('boots.new')}
          </Button>
        </div>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('boots.search')} />
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
          value={f.street}
          onChange={(v) => list.set('street', v)}
          className="w-48"
          options={[
            { value: ALL, label: t('boots.streetAll') },
            { value: 'yes', label: t('boots.streetYes') },
            { value: 'no', label: t('boots.streetNo') },
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
            <Download /> {t('boots.downloadSelected', { count: picked.length })}
          </Button>
          <Button variant="outline" size="sm" disabled={!picked.length} onClick={() => setDeleting(true)}>
            <Trash2 /> {t('boots.deleteSelected', { count: picked.length })}
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
                aria-label={t('boots.selectAll')}
                onCheckedChange={(v) => {
                  if (v === true) setAskAll(true)
                  else setSelected(new Set())
                }}
              />
            </TableHead>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('boots.colCredits')}</TableHead>
            <TableHead>{t('boots.colStreet')}</TableHead>
            <TableHead>{t('boots.colWearers')}</TableHead>
            <TableHead>{t('boots.colCode')}</TableHead>
            <DateHeads />
            <TableHead className="w-12" />
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={10} className="py-8 text-center text-muted-foreground">
                {originalsQuery.error
                  ? t('boots.originalsFailed', { error: originalsQuery.error.message })
                  : originals === undefined
                    ? t('common.loading')
                    : t('boots.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((r) => {
            if (r.kind === 'original') {
              const b = r.boot
              return (
                <TableRow key={rowKey(r)} className="cursor-pointer text-muted-foreground" title={t('boots.editOriginalHint')} onClick={() => navigate(bootPath(b.code), from)}>
                  <TableCell />
                  <TableCell data-grow>
                    <span className="flex items-center gap-2">
                      <BootThumb code={b.code} />
                      <span className="text-foreground">Original {b.code}</span>
                      <OriginalBadge />
                    </span>
                  </TableCell>
                  <TableCell>EA</TableCell>
                  <TableCell>{b.street ? t('boots.yes') : t('boots.no')}</TableCell>
                  <TableCell className="tabular-nums" title={t('boots.gameWearersHint')}>
                    {b.players}
                  </TableCell>
                  <TableCell className="tabular-nums">{b.code}</TableCell>
                  <DateCells />
                  <TableCell />
                  <TableCell />
                </TableRow>
              )
            }
            const b = r.boot
            const original = b.original_id != null
            const users = wearers(draft, original ? { original_id: b.original_id! } : b).length
            return (
              <TableRow key={rowKey(r)} className="cursor-pointer" onClick={() => navigate(bootPath(bootKey(b)), from)}>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox checked={selected.has(b.uid)} onCheckedChange={() => toggle(b.uid)} aria-label={t('boots.select')} />
                </TableCell>
                <TableCell data-grow className={b.hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                  <span className="flex items-center gap-2">
                    <BootThumb boot={b} />
                    {b.name.trim() || <span className="text-muted-foreground">{t('common.unnamed')}</span>}
                    {original && <OriginalBadge entry={b.uid} />}
                    {b.hidden && <OutOfPatchBadge />}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">{b.credits || '—'}</TableCell>
                <TableCell>
                  {(original ? b.original_id! >= 500 && b.original_id! <= 619 : b.street) ? t('boots.yes') : t('boots.no')}
                </TableCell>
                <TableCell className="tabular-nums">{users || '—'}</TableCell>
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
                          if (b.hidden && b.street && !slots.free) {
                            toast.error(t('boots.streetFull', { total: slots.total }))
                            return
                          }
                          updateBoot(b.uid, { hidden: !b.hidden })
                        }}
                        hideHint={t('boots.hideHint')}
                        showHint={t('boots.showHint')}
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
            <AlertDialogTitle>{t('boots.selectAllTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('boots.selectAllDescription', { page: pageKeys.length, all: allKeys.length })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button variant="outline" onClick={() => selectMany(pageKeys)}>
              {t('boots.selectPage', { count: pageKeys.length })}
            </Button>
            <AlertDialogAction onClick={() => selectMany(allKeys)}>{t('boots.selectEvery', { count: allKeys.length })}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('boots.deleteTitle', { count: picked.length })}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                {inUse.length > 0 && <p>{t('boots.deleteWornMany')}</p>}
                {inUse.length > 0 && (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {inUse.map(({ boot, users }) => (
                      <li key={boot.uid}>
                        <span className="font-medium text-foreground">{bootName(boot, t('common.unnamed'))}</span>:{' '}
                        {users
                          .map(({ player, surfaces }) => `${playerName(player, t('common.unnamed'))} (${surfaces.map((s) => t(SURFACE_LABELS[s])).join(', ')})`)
                          .join('; ')}
                      </li>
                    ))}
                  </ul>
                )}
                <p>{t('boots.deleteDescription')}</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removeBoots(picked.map((b) => b.uid)) // also takes them off their players
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
