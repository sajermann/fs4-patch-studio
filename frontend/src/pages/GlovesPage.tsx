import { ZipImportButton } from '@/components/common/share'
import { DateCells, DateHeads } from '@/components/common/dates'
import { Download, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Glove, OriginalGlove } from '@/api/types'
import { GloveThumb } from '@/components/common/GloveThumb'
import { EntityIssues, OriginalBadge } from '@/components/common/form'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, matches, Pager, ScrollTable, SearchInput, useListParams, usePage } from '@/components/common/list'
import { CreditsLink } from '@/components/common/CreditsLink'
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
import { admitImported, gloveKey, gloveName, glovePath, useGloveSlots, wearers } from '@/lib/gloves'
import { playerName } from '@/lib/players'
import { newUid, useProject, useSameAsGame } from '@/state/project'
import { useOriginalGloves } from '@/state/queries'

type Row = { kind: 'project'; glove: Glove } | { kind: 'original'; glove: OriginalGlove }

const rowKey = (r: Row) => (r.kind === 'project' ? r.glove.uid : `game-${r.glove.code}`)

export function GlovesPage() {
  const { t } = useI18n()
  const { draft, dirty, addGloves, updateGlove, removeGloves, save } = useProject()
  const originalsQuery = useOriginalGloves()
  const originals = originalsQuery.data
  const navigate = useNavigate()
  const from = useFrom(t('nav.gloves'))
  const list = useListParams(['q', 'origin', 'status'] as const)
  const f = list.values
  const slots = useGloveSlots()
  const sameAsGame = useSameAsGame()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [askAll, setAskAll] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)

  // the game's gloves edited in the project show once, as their entry; ones only opened list as the game's
  const mine = (draft.gloves ?? []).filter((g) => !sameAsGame(g.uid))
  const edited = new Map(mine.filter((g) => g.original_id != null).map((g) => [g.original_id!, g]))
  const rows: Row[] = [
    ...mine.map((glove) => ({ kind: 'project' as const, glove })),
    ...(originals ?? []).filter((g) => !edited.has(g.code)).map((glove) => ({ kind: 'original' as const, glove })),
  ].filter((r) => {
    const name = r.kind === 'project' ? r.glove.name : `Original ${r.glove.code}`
    const credits = r.kind === 'project' ? r.glove.credits : 'EA'
    const code = r.kind === 'project' ? (r.glove.original_id ?? r.glove.code) : r.glove.code
    return (
      matches(f.q, name, credits, code != null ? String(code) : undefined) &&
      (f.origin === ALL || f.origin === r.kind) &&
      (f.status === ALL || (f.status === 'hidden') === (r.kind === 'project' && !!r.glove.hidden))
    )
  })
  const page = usePage(rows, list.page, list.pageSize)
  const selectable = (r: Row) => r.kind === 'project'
  const pageKeys = page.rows.filter(selectable).map(rowKey)
  const allKeys = rows.filter(selectable).map(rowKey)
  const allOnPage = pageKeys.length > 0 && pageKeys.every((k) => selected.has(k))
  const picked = mine.filter((g) => selected.has(g.uid))
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
      toast.error(t('gloves.slotsFull', { total: slots.total }))
      return
    }
    const uid = newUid()
    addGloves([{ uid, name: '' }])
    navigate(glovePath(uid), from)
  }

  const download = async () => {
    const exportable = picked.filter((g) => g.original_id == null || g.texture)
    if (exportable.length < picked.length) toast.warning(t('gloves.downloadSkipsGame', { count: picked.length - exportable.length }))
    if (!exportable.length) return
    setBusy(true)
    try {
      if (dirty) await save()
      const { name, blob } = await api.exportGloves(
        exportable.map((g) => g.uid),
        exportable.length > 1,
      )
      saveBlob(name, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('gloves.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const inUse = picked.map((g) => ({ glove: g, users: wearers(draft, g) })).filter((u) => u.users.length && u.glove.original_id == null)

  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.gloves')}</h1>
          <p className="text-sm text-muted-foreground">{t('gloves.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={slots.free ? 'secondary' : 'destructive'} className="font-normal" title={t('gloves.slotsHint', { total: slots.total })}>
            {t('gloves.slots', { used: slots.used, total: slots.total })}
          </Badge>
          <ZipImportButton
            kind="gloves"
            read={async (file) => {
              const r = await api.importGloves(file)
              return { items: r.gloves, problems: r.problems }
            }}
            // an entry it replaces gives its code back
            admit={(items, replaced) => admitImported(items as Glove[], slots.free + replaced.filter((g) => !(g as Glove).hidden && (g as Glove).original_id == null).length)}
            label={t('gloves.importMany')}
            hint={t('gloves.importManyHint')}
          />
          <Button onClick={create}>
            <Plus /> {t('gloves.new')}
          </Button>
        </div>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('gloves.search')} />
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
            <Download /> {t('gloves.downloadSelected', { count: picked.length })}
          </Button>
          <Button variant="outline" size="sm" disabled={!picked.length} onClick={() => setDeleting(true)}>
            <Trash2 /> {t('gloves.deleteSelected', { count: picked.length })}
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
                aria-label={t('gloves.selectAll')}
                onCheckedChange={(v) => {
                  if (v === true) setAskAll(true)
                  else setSelected(new Set())
                }}
              />
            </TableHead>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('gloves.colCredits')}</TableHead>
            <TableHead>{t('gloves.colWearers')}</TableHead>
            <TableHead>{t('gloves.colCode')}</TableHead>
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
                  ? t('gloves.originalsFailed', { error: originalsQuery.error.message })
                  : originals === undefined
                    ? t('common.loading')
                    : t('gloves.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((r) => {
            if (r.kind === 'original') {
              const g = r.glove
              return (
                <TableRow key={rowKey(r)} className="cursor-pointer text-muted-foreground" title={t('gloves.editOriginalHint')} onClick={() => navigate(glovePath(g.code), from)}>
                  <TableCell />
                  <TableCell data-grow>
                    <span className="flex items-center gap-2">
                      <GloveThumb code={g.code} />
                      <span className="text-foreground">Original {g.code}</span>
                      <OriginalBadge />
                    </span>
                  </TableCell>
                  <TableCell>EA</TableCell>
                  <TableCell className="tabular-nums" title={t('gloves.gameWearersHint')}>
                    {g.players}
                  </TableCell>
                  <TableCell className="tabular-nums">{g.code}</TableCell>
                  <DateCells />
                  <TableCell />
                  <TableCell />
                </TableRow>
              )
            }
            const g = r.glove
            const original = g.original_id != null
            const users = wearers(draft, original ? { original_id: g.original_id! } : g).length
            return (
              <TableRow key={rowKey(r)} className="cursor-pointer" onClick={() => navigate(glovePath(gloveKey(g)), from)}>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox checked={selected.has(g.uid)} onCheckedChange={() => toggle(g.uid)} aria-label={t('gloves.select')} />
                </TableCell>
                <TableCell data-grow className={g.hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                  <span className="flex items-center gap-2">
                    <GloveThumb glove={g} />
                    {g.name.trim() || <span className="text-muted-foreground">{t('common.unnamed')}</span>}
                    {original && <OriginalBadge entry={g.uid} />}
                    {g.hidden && <OutOfPatchBadge />}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  <CreditsLink credits={g.credits} url={g.credits_url} empty="—" />
                </TableCell>
                <TableCell className="tabular-nums">{users || '—'}</TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{g.original_id ?? g.code ?? t('common.auto')}</TableCell>
                <DateCells entry={g} />
                <TableCell>
                  <EntityIssues uid={g.uid} />
                </TableCell>
                <TableCell>
                  <span className="flex items-center justify-end gap-1">
                    {!original && (
                      <HideButton
                        hidden={!!g.hidden}
                        onToggle={() => {
                          if (g.hidden && !slots.free) {
                            toast.error(t('gloves.slotsFull', { total: slots.total }))
                            return
                          }
                          updateGlove(g.uid, { hidden: !g.hidden })
                        }}
                        hideHint={t('gloves.hideHint')}
                        showHint={t('gloves.showHint')}
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
            <AlertDialogTitle>{t('gloves.selectAllTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('gloves.selectAllDescription', { page: pageKeys.length, all: allKeys.length })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button variant="outline" onClick={() => selectMany(pageKeys)}>
              {t('gloves.selectPage', { count: pageKeys.length })}
            </Button>
            <AlertDialogAction onClick={() => selectMany(allKeys)}>{t('gloves.selectEvery', { count: allKeys.length })}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('gloves.deleteTitle', { count: picked.length })}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                {inUse.length > 0 && <p>{t('gloves.deleteWornMany')}</p>}
                {inUse.length > 0 && (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {inUse.map(({ glove, users }) => (
                      <li key={glove.uid}>
                        <span className="font-medium text-foreground">{gloveName(glove, t('common.unnamed'))}</span>:{' '}
                        {users.map((p) => playerName(p, t('common.unnamed'))).join(', ')}
                      </li>
                    ))}
                  </ul>
                )}
                <p>{t('gloves.deleteDescription')}</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removeGloves(picked.map((g) => g.uid)) // also takes them off their players
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
