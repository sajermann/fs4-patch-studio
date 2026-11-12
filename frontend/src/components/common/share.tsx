import { Download, FileUp, Trash2 } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Dated, ShareKind, ShareProblem } from '@/api/types'
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
import { useDateText } from '@/components/common/dates'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { hasMessage, useI18n, type MessageKey, type TFunction } from '@/i18n'
import { analyzeShare, entryName, mergeShared, planSingle, replaceEntry, type ImportKind, type ShareAnalysis, type SharedEntry } from '@/lib/share'
import { useKeepBack } from '@/lib/back'
import { useProject } from '@/state/project'

// ---------------------------------------------------------------- selection in the lists
/** Rows picked by their checkbox; the header one asks "this page or every page". */
export function useListSelection(pageKeys: string[], allKeys: string[]) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [askAll, setAskAll] = useState(false)
  const toggle = (key: string) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const pick = (keys: string[]) => {
    setSelected((s) => new Set([...s, ...keys]))
    setAskAll(false)
  }
  const allOnPage = pageKeys.length > 0 && pageKeys.every((k) => selected.has(k))
  return { selected, toggle, clear: () => setSelected(new Set()), allOnPage, askAll, setAskAll, pick, pageKeys, allKeys }
}
export type ListSelection = ReturnType<typeof useListSelection>

export function SelectAllCheckbox({ selection }: { selection: ListSelection }) {
  const { t } = useI18n()
  return (
    <Checkbox
      checked={selection.allOnPage}
      disabled={!selection.pageKeys.length}
      aria-label={t('share.selectAll')}
      onCheckedChange={(v) => {
        if (v === true) selection.setAskAll(true)
        else selection.clear()
      }}
    />
  )
}

export function RowCheckbox({ selection, value }: { selection: ListSelection; value: string }) {
  const { t } = useI18n()
  return (
    <span onClick={(e) => e.stopPropagation()}>
      <Checkbox checked={selection.selected.has(value)} onCheckedChange={() => selection.toggle(value)} aria-label={t('share.select')} />
    </span>
  )
}

export function SelectAllDialog({ selection }: { selection: ListSelection }) {
  const { t } = useI18n()
  return (
    <AlertDialog open={selection.askAll} onOpenChange={selection.setAskAll}>
      {/* wider than the default: three buttons with counts do not fit in max-w-sm */}
      <AlertDialogContent className="data-[size=default]:max-w-[calc(100%-2rem)] data-[size=default]:sm:max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('share.selectAllTitle')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('share.selectAllDescription', { page: selection.pageKeys.length, all: selection.allKeys.length })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <Button variant="outline" onClick={() => selection.pick(selection.pageKeys)}>
            {t('share.selectPage', { count: selection.pageKeys.length })}
          </Button>
          <AlertDialogAction onClick={() => selection.pick(selection.allKeys)}>
            {t('share.selectEvery', { count: selection.allKeys.length })}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** "Download (n)" and "Delete (n)" of the selected rows, with the delete confirmation. */
export function BulkActions({
  kind,
  selection,
  picked,
  onDelete,
}: {
  kind: ShareKind
  selection: ListSelection
  picked: string[] // uids of the selected project entries
  onDelete: (uids: string[]) => void | Promise<void>
}) {
  const { t } = useI18n()
  const { busy, download } = useShareDownload(kind)
  // the entries picked when the confirmation opened (the count stays while it closes)
  const [deleting, setDeleting] = useState<string[] | null>(null)
  return (
    <div className="ml-auto flex gap-2">
      <Button variant="outline" size="sm" disabled={!picked.length || busy} onClick={() => void download(picked)}>
        <Download /> {t('share.downloadSelected', { count: picked.length })}
      </Button>
      <Button variant="outline" size="sm" disabled={!picked.length} onClick={() => setDeleting(picked)}>
        <Trash2 /> {t('share.deleteSelected', { count: picked.length })}
      </Button>
      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('share.deleteTitle', { count: deleting?.length ?? 0 })}</AlertDialogTitle>
            <AlertDialogDescription>{t(`share.deleteDescription.${kind}` as MessageKey)}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                if (deleting) await onDelete(deleting)
                selection.clear()
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

// ---------------------------------------------------------------- download
/** Downloads saved entries in a shared zip (saves the project first). */
export function useShareDownload(kind: ShareKind) {
  const { t } = useI18n()
  const { dirty, save } = useProject()
  const [busy, setBusy] = useState(false)
  const download = async (uids: string[]) => {
    if (!uids.length) return
    setBusy(true)
    try {
      if (dirty) await save()
      const { name, blob } = await api.exportShare(kind, uids)
      saveBlob(name, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }
  return { busy, download }
}

/** "Download zip" on an entry's page; an original only opened (nothing changed) has nothing to share. */
export function ShareDownloadButton({ kind, uid, unchanged }: { kind: ShareKind; uid: string; unchanged?: boolean }) {
  const { t } = useI18n()
  const { busy, download } = useShareDownload(kind)
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={busy || unchanged}
      title={unchanged ? t('share.downloadUnchanged') : t('share.downloadHint')}
      onClick={() => void download([uid])}
    >
      <Download /> {t('share.download')}
    </Button>
  )
}

// ---------------------------------------------------------------- import
interface Pending {
  token?: string
  items: SharedEntry[]
  problems: ShareProblem[]
  analysis: ShareAnalysis
}

/** "Import zip" of a list: reads the zip, imports right away when nothing needs a look, otherwise shows what each
 * entry replaces (side by side, with their dates), the links not found and the files with problems, and imports on
 * the user's go. Saves after.
 * - read: what the zip holds (nothing in the project changes yet; files may already be provisional uploads)
 * - finish: the entries ready for the project (leagues/teams/players: the backend stores their files now)
 * - admit: last touch before they join (boots/gloves/balls: out of the patch when no code is left), given the
 *   project entries they replace */
export function ZipImportButton({
  kind,
  read,
  finish,
  admit,
  label,
  hint,
}: {
  kind: ImportKind
  read: (file: File) => Promise<{ token?: string; items: SharedEntry[]; problems: ShareProblem[] }>
  finish?: (p: Pending) => Promise<SharedEntry[]>
  admit?: (items: SharedEntry[], replaced: SharedEntry[]) => SharedEntry[]
  label?: string
  hint?: string
}) {
  const { t } = useI18n()
  const { draft, setDraft, requestSave } = useProject()
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const input = useRef<HTMLInputElement>(null)

  const apply = async (p: Pending) => {
    setPending(null)
    setBusy(true)
    try {
      const got = finish ? await finish(p) : p.items
      const items = admit ? admit(got, [...p.analysis.replaces.values()]) : got
      const hidden = (e: SharedEntry) => !!(e as { hidden?: boolean }).hidden
      const out = items.filter((e, k) => hidden(e) && !hidden(got[k])).length
      setDraft((project) => mergeShared(kind, project, items, p.analysis))
      requestSave()
      const ignored = [...p.analysis.missing.values()].reduce((n, l) => n + l.length, 0)
      toast.success(t('share.imported', { count: items.length }), {
        description: [
          p.analysis.replaces.size ? t('share.importedReplaced', { count: p.analysis.replaces.size }) : '',
          ignored ? t('share.importedIgnored', { count: ignored }) : '',
          out ? t('share.importedOut', { count: out }) : '',
        ]
          .filter(Boolean)
          .join(' '),
      })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const readZip = async (file: File) => {
    setBusy(true)
    try {
      const r = await read(file)
      if (!r.items.length) {
        // one message with every problem of the zip, one per line
        toast.error(t('share.nothing'), { description: problemLines(t, r.problems), classNames: { description: 'whitespace-pre-line' } })
        return
      }
      const p = { ...r, analysis: analyzeShare(kind, draft, r.items) }
      const quiet = !p.problems.length && !p.analysis.replaces.size && !p.analysis.missing.size && !p.analysis.waitingPlayers.size
      setBusy(false)
      if (quiet) await apply(p)
      else setPending(p)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) void readZip(file)
        }}
      />
      <Button variant="outline" disabled={busy} title={hint} onClick={() => input.current?.click()}>
        <FileUp /> {label ?? t('share.import')}
      </Button>
      <ShareImportDialog kind={kind} pending={pending} selectable onCancel={() => setPending(null)} onConfirm={(p) => void apply(p)} />
    </>
  )
}

/** "Import zip" of the leagues, teams and players lists (backend share_service: inspect, then apply). */
export function ShareImportButton({ kind }: { kind: ShareKind }) {
  const { t } = useI18n()
  return (
    <ZipImportButton
      kind={kind}
      read={(file) => api.inspectShare<SharedEntry>(kind, file)}
      finish={async (p) => (await api.applyShare<SharedEntry>(kind, p.token!, p.items.map((i) => i.uid))).items}
      hint={t(`share.importHint.${kind}` as MessageKey)}
    />
  )
}

/** "Upload zip" on an entry's page: the zip's one entry fills this one (lib/share planSingle says when it may):
 * while creating it, right away (it takes the zip's uid); when editing, after the same review as the lists. Saves
 * after, and opens the entry's own address when it changed (a new uid, or the edit of a game entry).
 * - finish: the entry ready for the project, given the uid it takes (leagues/teams/players: the backend stores its
 *   files under that uid); admit: last touch (boots/gloves/balls: out of the patch when no code is left) */
export function SingleZipImport({
  kind,
  entry,
  read,
  finish,
  admit,
  pathOf,
  label,
  hint,
}: {
  kind: ImportKind
  entry: SharedEntry
  read: (file: File) => Promise<{ token?: string; items: SharedEntry[]; problems: ShareProblem[] }>
  finish?: (p: Pending, uid: string) => Promise<SharedEntry>
  admit?: (item: SharedEntry, replaced: SharedEntry | null) => SharedEntry
  pathOf: (e: SharedEntry) => string
  label?: string
  hint?: string
}) {
  const { t } = useI18n()
  const { draft, setDraft, requestSave, savedUids } = useProject()
  const navigate = useNavigate()
  const keepBack = useKeepBack()
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<(Pending & { uid: string; mode: 'create' | 'edit' }) | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const unnamed = t('common.unnamed')

  const apply = async (p: Pending & { uid: string; mode: 'create' | 'edit' }) => {
    setPending(null)
    setBusy(true)
    try {
      const incoming = p.items[0]
      const got = finish ? await finish(p, p.uid) : { ...incoming, uid: p.uid }
      const item = admit ? admit(got, p.mode === 'edit' ? entry : null) : got
      setDraft((project) => replaceEntry(kind, project, entry.uid, item, p.analysis, incoming.uid))
      requestSave()
      const ignored = [...p.analysis.missing.values()].reduce((n, l) => n + l.length, 0)
      toast.success(t('share.single.done'), { description: ignored ? t('share.importedIgnored', { count: ignored }) : undefined })
      if (pathOf(item) !== pathOf(entry)) navigate(pathOf(item), { ...keepBack, replace: true })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const readZip = async (file: File) => {
    setBusy(true)
    try {
      const r = await read(file)
      if (r.items.length !== 1) {
        toast.error(r.items.length ? t('share.single.many', { count: r.items.length }) : t('share.nothing'), {
          description: problemLines(t, r.problems),
          classNames: { description: 'whitespace-pre-line' },
        })
        return
      }
      const incoming = r.items[0]
      const plan = planSingle(kind, draft, savedUids, entry, incoming)
      if (!plan.ok) {
        toast.error(t(`share.single.${plan.reason}` as MessageKey, { name: plan.other ? entryName(kind, plan.other) || unnamed : '' }))
        return
      }
      const found = analyzeShare(kind, draft, r.items)
      const analysis = { ...found, replaces: new Map(plan.mode === 'edit' ? [[incoming.uid, entry]] : []) }
      const p = { ...r, analysis, uid: plan.uid, mode: plan.mode }
      const quiet = plan.mode === 'create' && !p.problems.length && !analysis.missing.size && !analysis.waitingPlayers.size
      setBusy(false)
      if (quiet) await apply(p)
      else setPending(p)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) void readZip(file)
        }}
      />
      <Button variant="outline" size="sm" disabled={busy} title={hint ?? t('share.single.hint')} onClick={() => input.current?.click()}>
        <FileUp /> {label ?? t('share.single.button')}
      </Button>
      <ShareImportDialog kind={kind} pending={pending} onCancel={() => setPending(null)} onConfirm={(p) => void apply(p)} />
    </>
  )
}

/** "Upload zip" on a league, team or player page (backend share_service: inspect, then apply under the page's uid). */
export function ShareSingleImport({ kind, entry, pathOf }: { kind: ShareKind; entry: SharedEntry; pathOf: (e: SharedEntry) => string }) {
  return (
    <SingleZipImport
      kind={kind}
      entry={entry}
      pathOf={pathOf}
      read={(file) => api.inspectShare<SharedEntry>(kind, file)}
      finish={async (p, uid) => {
        const zipUid = p.items[0].uid
        return (await api.applyShare<SharedEntry>(kind, p.token!, [zipUid], { [zipUid]: uid })).items[0]
      }}
    />
  )
}

/** A problem of an imported file in the interface language (by its code when the app knows it). */
function problemText(t: TFunction, p: ShareProblem) {
  for (const key of [`share.problem.${p.code}`, `apiError.${p.code}`]) if (hasMessage(key)) return t(key)
  return p.message
}

/** The problems of a zip as one text, one per line ("name: problem"); undefined when there are none. */
function problemLines(t: TFunction, problems: ShareProblem[]) {
  return problems.map((p) => `${p.name || t('common.unnamed')}: ${problemText(t, p)}`).join('\n') || undefined
}

/** A titled part of the import review. `scroll`: the children scroll on their own (title and description stay put)
 * and the section shrinks to share the dialog's height with the other lists. */
function Section({ title, description, scroll, children }: { title: string; description?: string; scroll?: boolean; children: ReactNode }) {
  return (
    <section className={scroll ? 'flex min-h-0 flex-col gap-1.5' : 'shrink-0 space-y-1.5'}>
      <h3 className="shrink-0 text-sm font-medium">{title}</h3>
      {description && <p className="shrink-0 text-xs text-muted-foreground">{description}</p>}
      {scroll ? <div className="min-h-0 overflow-y-auto">{children}</div> : children}
    </section>
  )
}

function Dates({ entry }: { entry: Dated }) {
  const { t } = useI18n()
  const text = useDateText()
  if (!entry.created_at && !entry.updated_at) return <span className="text-xs text-muted-foreground">{t('share.noDate')}</span>
  return (
    <span className="flex flex-col text-xs text-muted-foreground">
      {entry.created_at && <span>{t('dates.created', { date: text(entry.created_at) })}</span>}
      {entry.updated_at && <span>{t('dates.updated', { date: text(entry.updated_at) })}</span>}
    </span>
  )
}

/** The pending import with only the picked entries (the analysis is per entry, so filtering it is exact). */
function onlyPicked<P extends Pending>(p: P, skipped: Set<string>): P {
  if (!skipped.size) return p
  const keep = (uid: string) => !skipped.has(uid)
  return {
    ...p,
    items: p.items.filter((i) => keep(i.uid)),
    analysis: {
      replaces: new Map([...p.analysis.replaces].filter(([uid]) => keep(uid))),
      missing: new Map([...p.analysis.missing].filter(([uid]) => keep(uid))),
      waitingPlayers: new Set([...p.analysis.waitingPlayers].filter(keep)),
    },
  }
}

/** The review before an import. With `selectable` (the lists' import), every zip entry has a checkbox: the
 * unchecked ones stay out (they are not sent to the backend nor merged). */
function ShareImportDialog<P extends Pending>({
  kind,
  pending,
  onCancel,
  onConfirm,
  selectable = false,
}: {
  kind: ImportKind
  pending: P | null
  onCancel: () => void
  onConfirm: (p: P) => void
  selectable?: boolean
}) {
  const { t } = useI18n()
  const [skipped, setSkipped] = useState<Set<string>>(new Set())
  // a new zip starts with everything checked
  const [seen, setSeen] = useState<P | null>(null)
  if (pending !== seen) {
    setSeen(pending)
    setSkipped(new Set())
  }
  const unnamed = t('common.unnamed')
  const name = (e: SharedEntry) => entryName(kind, e) || unnamed
  const items = pending?.items ?? []
  const byUid = new Map(items.map((i) => [i.uid, i]))
  const replaces = pending ? [...pending.analysis.replaces] : []
  const fresh = selectable ? items.filter((i) => !pending!.analysis.replaces.has(i.uid)) : []
  const missing = pending ? [...pending.analysis.missing] : []
  const picked = items.length - skipped.size
  const isOut = (uid: string) => selectable && skipped.has(uid)
  const toggle = (uid: string) =>
    setSkipped((s) => {
      const next = new Set(s)
      if (next.has(uid)) next.delete(uid)
      else next.add(uid)
      return next
    })
  // the whole row toggles too: the checkbox's own click must not reach the row and toggle twice
  const pick = (uid: string) =>
    selectable && (
      <span onClick={(e) => e.stopPropagation()}>
        <Checkbox className="mt-0.5" checked={!skipped.has(uid)} onCheckedChange={() => toggle(uid)} aria-label={t('share.pickItem')} />
      </span>
    )
  const rowProps = (uid: string) =>
    selectable ? { onClick: () => toggle(uid), className: `cursor-pointer select-none ${isOut(uid) ? 'opacity-50' : ''}` } : {}
  const missingPicked = missing.some(([uid]) => !isOut(uid))
  const linkText = (m: { kind: 'team' | 'league' | 'boot' | 'glove'; ref: string }) => t(`share.missing.${m.kind}` as MessageKey, { ref: m.ref })
  return (
    <Dialog open={!!pending} onOpenChange={(open) => !open && onCancel()}>
      {/* only the lists scroll: the header, the notes under them and the buttons stay in view */}
      <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-2xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>{t('share.dialogTitle', { count: items.length })}</DialogTitle>
          <DialogDescription>{t(selectable ? 'share.dialogDescriptionPick' : 'share.dialogDescription')}</DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-col gap-4 text-sm">
          {selectable && items.length > 1 && (
            <label className="flex w-fit shrink-0 cursor-pointer items-center gap-2 text-xs text-muted-foreground">
              <Checkbox
                checked={skipped.size === 0 ? true : picked === 0 ? false : 'indeterminate'}
                onCheckedChange={(v) => setSkipped(v === true ? new Set() : new Set(items.map((i) => i.uid)))}
              />
              {t('share.pickAll')}
            </label>
          )}
          {replaces.length > 0 && (
            <Section scroll title={t('share.replacesTitle', { count: replaces.length })} description={t('share.replacesDescription')}>
              <table className="w-full text-left">
                <thead className="sticky top-0 z-10 bg-popover text-xs text-muted-foreground">
                  <tr>
                    {selectable && <th className="w-6 py-1 pr-2" />}
                    <th className="py-1 pr-3 font-normal">{t('share.colCurrent')}</th>
                    <th className="py-1 font-normal">{t('share.colIncoming')}</th>
                  </tr>
                </thead>
                <tbody>
                  {replaces.map(([uid, current]) => {
                    const incoming = byUid.get(uid)!
                    return (
                      <tr key={uid} onClick={rowProps(uid).onClick} className={`border-t align-top ${rowProps(uid).className ?? ''}`}>
                        {selectable && <td className="py-1.5 pr-2">{pick(uid)}</td>}
                        <td className="py-1.5 pr-3">
                          <div className="font-medium">{name(current)}</div>
                          <Dates entry={current} />
                        </td>
                        <td className="py-1.5">
                          <div className="font-medium">{name(incoming)}</div>
                          <Dates entry={incoming} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </Section>
          )}
          {fresh.length > 0 && (
            <Section scroll title={t('share.newTitle', { count: fresh.length })}>
              <ul className="space-y-1">
                {fresh.map((item) => (
                  <li key={item.uid} onClick={rowProps(item.uid).onClick} className={`flex items-start gap-2 border-t pt-1.5 ${rowProps(item.uid).className ?? ''}`}>
                    {pick(item.uid)}
                    <div>
                      <div className="font-medium">{name(item)}</div>
                      <Dates entry={item} />
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {missing.length > 0 && (
            <Section title={t('share.missingTitle', { count: missing.length })} description={t('share.missingDescription')}>
              <ul className="max-h-32 space-y-1 overflow-y-auto">
                {missing.map(([uid, links]) => (
                  <li key={uid} className={isOut(uid) ? 'opacity-50' : ''}>
                    <span className="font-medium">{name(byUid.get(uid)!)}</span>: {links.map(linkText).join(', ')}
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {pending && pending.analysis.waitingPlayers.size > 0 && (
            <p className="shrink-0 text-muted-foreground">{t('share.waitingPlayers', { count: pending.analysis.waitingPlayers.size })}</p>
          )}
          {pending && pending.problems.length > 0 && (
            <Section title={t('share.problemsTitle', { count: pending.problems.length })}>
              <ul className="max-h-32 space-y-1 overflow-y-auto">
                {pending.problems.map((p, k) => (
                  <li key={k}>
                    <span className="font-medium">{p.name || unnamed}</span>: {problemText(t, p)}
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {(missing.length > 0 || (pending?.analysis.waitingPlayers.size ?? 0) > 0) && (
            <p className="shrink-0 rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground">{t('share.order')}</p>
          )}
        </div>
        <DialogFooter className="shrink-0">
          <Button variant="outline" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button disabled={selectable && picked === 0} onClick={() => pending && onConfirm(onlyPicked(pending, skipped))}>
            {missingPicked
              ? t('share.confirmIgnoring')
              : selectable && skipped.size > 0
                ? t('share.confirmCount', { count: picked })
                : t('share.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
