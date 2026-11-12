import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check, FolderOpen, LoaderCircle, Settings, Undo2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { ApiError, api, faceThumbUrl } from '@/api/client'
import type { FacePackFace, FacePackSummary, Player, ScannedFace } from '@/api/types'
import { CreditsLink } from '@/components/common/CreditsLink'
import { ALL, FilterSelect, Pager, SearchInput } from '@/components/common/list'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useStatus } from '@/state/queries'

/** Face of a pack being looked at in the 3D preview (not picked yet). */
export interface BrowsedFace {
  folder: string
  face: FacePackFace
}

// Real faces from FIFA 14-16 packs (user's choice, 21/10): the packs stay where the user keeps them (the backend
// reads them in place; the folders are set in the settings, several since 12/11); the gallery shows each face from
// the front, one page at a time (the backend pages and searches: there may be thousands of faces); clicking one shows
// it converted in the 3D preview; "use this face" copies only that face's files into the project. Who the face is
// and who made it come from the pack's manifest.json (12/11; before, from the players base): a face it does not list
// shows only its id. The same id may exist in two packs: a face is its folder + id. "Browse another folder" (24/10,
// kept on 12/11 at the user's request) shows only the faces of a folder picked here, for this visit (e.g. a face just
// downloaded, to try it without adding it to the settings); a face used from it is copied like any other.
const SEARCH_DELAY_MS = 300

const sameFace = (a: { folder: string; id: number }, b: { folder: string; id: number }) => a.folder === b.folder && a.id === b.id

export function FacePicker({
  player,
  browsing,
  onBrowse,
  unsupported = false,
  pickExtras,
}: {
  player: Player
  browsing: BrowsedFace | null
  onBrowse: (face: BrowsedFace | null) => void
  /** the face being looked at does not convert: it cannot be picked */
  unsupported?: boolean
  /** what "use this face" also sets: the face options and appearance chosen while looking at it */
  pickExtras?: { face?: Partial<ScannedFace>; appearance?: Record<string, number> }
}) {
  const { t } = useI18n()
  const { updatePlayer } = useProject()
  const folders = useStatus().data?.config.face_pack_dirs ?? []
  // folder picked here for this visit only (e.g. a face just downloaded): only its faces; leaving the screen forgets it
  const [otherDir, setOtherDir] = useState<string | null>(null)
  const [choosing, setChoosing] = useState(false)
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState('') // filter after the user stops typing
  const [pack, setPack] = useState(ALL)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [picking, setPicking] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(filter.trim())
      setPage(1)
    }, SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [filter])

  const pageQuery = useQuery({
    queryKey: ['facepack', otherDir ?? folders, search, pack, page, pageSize],
    queryFn: () =>
      api.facePage({
        offset: (page - 1) * pageSize,
        limit: pageSize,
        q: search,
        ...(otherDir ? { folder: otherDir } : { pack: pack === ALL ? undefined : pack }),
      }),
    enabled: !!otherDir || folders.length > 0,
    retry: false,
    placeholderData: keepPreviousData,
  })
  const data = pageQuery.data
  const packs: FacePackSummary[] = data?.packs ?? []
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize))

  const showFolder = (folder: string | null) => {
    setOtherDir(folder)
    setPack(ALL)
    setPage(1)
    onBrowse(null)
  }

  const browseOther = async () => {
    setChoosing(true)
    try {
      const { folder } = await api.browseFolder(otherDir ?? folders[folders.length - 1] ?? null)
      if (folder) showFolder(folder)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('folder.pickFailed'))
    } finally {
      setChoosing(false)
    }
  }

  const pick = async () => {
    if (!browsing) return
    setPicking(true)
    try {
      const { face } = await api.pickFace(browsing.folder, browsing.face.id, player.uid)
      updatePlayer(player.uid, {
        generic: false,
        face: { ...face, ...pickExtras?.face },
        ...(pickExtras?.appearance && { appearance: { ...player.appearance, ...pickExtras.appearance } }),
      })
      onBrowse(null)
      toast.success(t('faces.copied', { id: face.source_id }))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('faces.copyFailed'))
    } finally {
      setPicking(false)
    }
  }

  const current = player.face
  const isCurrent = (f: FacePackFace) => !!current && current.source_id === f.id && (!current.pack || current.pack === f.pack)
  const goToSettings = (label: string) => (
    <Button variant="outline" size="sm" asChild>
      <Link to="/settings">
        <Settings /> {label}
      </Link>
    </Button>
  )

  return (
    <div className="flex flex-col gap-3">
      {current && (
        <div className="flex items-center gap-3 rounded-md border p-2">
          <img src={faceThumbUrl({ player: player.uid, face: current.source_id })} alt="" className="size-14 rounded bg-muted object-contain" />
          <div className="min-w-0 text-sm">
            <p className="font-medium">
              {current.name ? `${current.name} · ` : ''}
              {t('faces.face', { id: current.source_id })}
            </p>
            <p className="truncate text-xs text-muted-foreground">{t('faces.copiedInProject', { pack: current.pack ?? t('faces.unknownPack') })}</p>
            {(current.credits || current.credits_url) && (
              <p className="truncate text-xs text-muted-foreground">
                {t('credits.by', { credits: '' })}
                <CreditsLink credits={current.credits} url={current.credits_url} />
              </p>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Button variant="outline" size="sm" onClick={() => void browseOther()} disabled={choosing}>
          {choosing ? <LoaderCircle className="animate-spin" /> : <FolderOpen />} {t('faces.browseOther')}
        </Button>
        {otherDir ? (
          <>
            <span className="min-w-0 truncate font-mono" title={otherDir}>
              {otherDir}
            </span>
            <Button variant="ghost" size="sm" onClick={() => showFolder(null)}>
              <Undo2 /> {folders.length ? t('faces.backToDefault') : t('faces.closeFolder')}
            </Button>
          </>
        ) : (
          <span>{t('faces.onlyThisScreen')}</span>
        )}
      </div>

      {!otherDir && !folders.length ? (
        <div className="flex flex-col items-start gap-2 rounded-md border border-dashed p-3 text-sm">
          <p className="text-muted-foreground">{t('faces.setPackFirst')}</p>
          {goToSettings(t('faces.goToSettings'))}
        </div>
      ) : pageQuery.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" /> {t('faces.opening')}
        </p>
      ) : pageQuery.error ? (
        <div className="flex flex-col items-start gap-2 rounded-md border border-destructive/40 p-3 text-sm">
          <p className="text-destructive">{pageQuery.error instanceof ApiError ? pageQuery.error.message : t('faces.openFailed')}</p>
          {!otherDir && goToSettings(t('faces.checkSettings'))}
        </div>
      ) : null}

      {data && (
        <div className="flex flex-col gap-2">
          <PackProblems packs={packs} />
          <div className="flex flex-wrap items-center gap-2">
            {packs.length > 1 && (
              <FilterSelect
                value={pack}
                onChange={(v) => {
                  setPack(v)
                  setPage(1)
                }}
                className="w-48"
                options={[
                  { value: ALL, label: t('faces.allPacks', { count: packs.reduce((n, p) => n + p.count, 0) }) },
                  ...packs.filter((p) => !p.error).map((p) => ({ value: p.folder, label: t('faces.packOption', { name: p.name, count: p.count }) })),
                ]}
              />
            )}
            <SearchInput value={filter} onChange={setFilter} placeholder={t('faces.filter')} className="min-w-40 flex-1" />
            {pageQuery.isFetching && <LoaderCircle className="size-4 animate-spin text-muted-foreground" />}
          </div>
          <div className="grid max-h-[26rem] grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-1.5 overflow-y-auto rounded-md border bg-muted/30 p-1.5">
            {data.items.map((f) => {
              const selected = !!browsing && sameFace({ folder: browsing.folder, id: browsing.face.id }, f)
              const choose = () => onBrowse(selected ? null : { folder: f.folder, face: f })
              return (
                <div
                  key={`${f.folder}|${f.id}`}
                  role="button"
                  tabIndex={0}
                  onClick={choose}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      choose()
                    }
                  }}
                  className={cn(
                    'relative flex cursor-pointer flex-col items-center rounded-md border bg-background p-1 text-xs hover:border-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                    selected && 'border-primary ring-2 ring-primary/40',
                  )}
                  title={[f.name, t('faces.face', { id: f.id }) + (f.hair ? '' : ` ${t('faces.noHair')}`), f.pack, f.credits && t('credits.by', { credits: f.credits })]
                    .filter(Boolean)
                    .join('\n')}
                >
                  <img
                    src={faceThumbUrl({ folder: f.folder, face: f.id })}
                    alt=""
                    loading="lazy"
                    className="aspect-square w-full object-contain"
                    onError={(e) => {
                      e.currentTarget.style.visibility = 'hidden' // a face the app cannot read: no broken image icon
                    }}
                  />
                  <span className="w-full truncate text-center text-[11px] leading-tight">{f.name ?? '—'}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{f.id}</span>
                  {(f.credits || f.credits_url) && (
                    <CreditsLink credits={f.credits} url={f.credits_url} className="max-w-full text-[10px] text-muted-foreground" />
                  )}
                  {isCurrent(f) && <Check className="absolute top-1 left-1 size-3.5 text-primary" />}
                </div>
              )
            })}
            {!data.items.length && <p className="col-span-full p-4 text-center text-xs text-muted-foreground">{t('faces.none')}</p>}
          </div>
          <Pager
            page={Math.min(page, pages)}
            pages={pages}
            total={data.total}
            pageSize={pageSize}
            onPage={(n, size = pageSize) => {
              setPage(n)
              setPageSize(size)
            }}
          />
        </div>
      )}

      {browsing && (
        <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/5 p-2 text-sm">
          {unsupported ? (
            <p className="min-w-0 flex-1 text-destructive">{t('faces.unsupported', { id: browsing.face.id })}</p>
          ) : (
            <p className="min-w-0 flex-1">
              {t('faces.viewing')}{' '}
              <span className="font-medium">{browsing.face.name ? `${browsing.face.name} (${browsing.face.id})` : browsing.face.id}</span>{' '}
              {t('faces.viewingRest')}
            </p>
          )}
          <Button size="sm" onClick={() => void pick()} disabled={picking || unsupported}>
            {picking ? <LoaderCircle className="animate-spin" /> : <Check />} {t('faces.use')}
          </Button>
          <Button size="icon" variant="ghost" className="size-8" onClick={() => onBrowse(null)} title={t('faces.stopViewing')}>
            <X />
          </Button>
        </div>
      )}
    </div>
  )
}

/** Folders of the settings without faces and problems of the packs' manifest.json (the gallery still works). */
export function PackProblems({ packs }: { packs: FacePackSummary[] }) {
  const { t } = useI18n()
  const lines = packs.flatMap((p) =>
    p.error
      ? [t('faces.packMissing', { folder: p.folder })]
      : p.warnings.map((w) => t('faces.manifestWarning', { pack: p.name, problem: t(`faces.warning.${w.code}`, { count: w.count ?? 0 }) })),
  )
  if (!lines.length) return null
  return (
    <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
      <AlertTriangle className="size-3.5 shrink-0" />
      <ul className="min-w-0 space-y-0.5">
        {lines.map((line, i) => (
          <li key={i} className="break-words">
            {line}
          </li>
        ))}
      </ul>
    </div>
  )
}
