import { useQuery } from '@tanstack/react-query'
import { Check, FolderOpen, LoaderCircle, Search, Settings, Undo2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, faceThumbUrl } from '@/api/client'
import type { FacePack, FacePackFace, Player } from '@/api/types'
import { matches } from '@/components/common/list'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useStatus } from '@/state/queries'

/** Face of a pack being looked at in the 3D preview (not picked yet). */
export interface BrowsedFace {
  folder: string
  face: FacePackFace
}

// Real faces from a FIFA 14 pack (user's choice, 21/10): the pack stays where the user keeps it (the backend reads
// it in place; the folder is set in the settings, 23/10); the gallery shows each face from the front (the
// pack's ids say nothing about who the player is); clicking one shows it converted in the 3D preview; "use this
// face" copies only that face's files into the project. "Browse another folder" (24/10) opens another pack only while
// this screen is open: leaving it goes back to the folder of the settings. Names (25/10): the backend tells who each
// face is from the EA players base (the face id is the EA player id); the gallery shows the name and searches by id
// or name (accents ignored).
const fold = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '')

export function FacePicker({ player, browsing, onBrowse }: { player: Player; browsing: BrowsedFace | null; onBrowse: (face: BrowsedFace | null) => void }) {
  const { t } = useI18n()
  const { updatePlayer } = useProject()
  const defaultDir = useStatus().data?.config.face_pack_dir
  const [otherDir, setOtherDir] = useState<string | null>(null) // folder picked here, for this visit only
  const packDir = otherDir ?? defaultDir
  const packQuery = useQuery({
    queryKey: ['facepack', packDir],
    queryFn: () => api.facePack(otherDir ?? undefined),
    enabled: !!packDir,
    retry: false,
  })
  const pack: FacePack | null = packQuery.data ?? null
  const [picking, setPicking] = useState(false)
  const [filter, setFilter] = useState('')
  const [choosing, setChoosing] = useState(false)

  const browseOther = async () => {
    setChoosing(true)
    try {
      const { folder } = await api.browseFolder(packDir)
      if (folder) {
        setOtherDir(folder)
        onBrowse(null)
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('folder.pickFailed'))
    } finally {
      setChoosing(false)
    }
  }

  const backToDefault = () => {
    setOtherDir(null)
    onBrowse(null)
  }

  const pick = async () => {
    if (!browsing) return
    setPicking(true)
    try {
      const { face } = await api.pickFace(browsing.folder, browsing.face.id, player.uid)
      updatePlayer(player.uid, { generic: false, face })
      onBrowse(null)
      toast.success(t('faces.copied', { id: face.source_id }))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('faces.copyFailed'))
    } finally {
      setPicking(false)
    }
  }

  const faces = useMemo(
    () => (pack?.faces ?? []).filter((f) => matches(fold(filter), String(f.id), f.player && fold(f.player.name))),
    [pack, filter],
  )
  const currentPlayer = player.face && pack?.faces.find((f) => f.id === player.face?.source_id)?.player

  return (
    <div className="flex flex-col gap-3">
      {player.face && (
        <div className="flex items-center gap-3 rounded-md border p-2">
          <img src={faceThumbUrl({ player: player.uid, face: player.face.source_id })} alt="" className="size-14 rounded bg-muted object-contain" />
          <div className="min-w-0 text-sm">
            <p className="font-medium">
              {currentPlayer ? `${currentPlayer.name} · ` : ''}
              {t('faces.face', { id: player.face.source_id })}
            </p>
            <p className="truncate text-xs text-muted-foreground">{t('faces.copiedInProject', { pack: player.face.pack ?? t('faces.unknownPack') })}</p>
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
            <Button variant="ghost" size="sm" onClick={backToDefault}>
              <Undo2 /> {defaultDir ? t('faces.backToDefault') : t('faces.closeFolder')}
            </Button>
          </>
        ) : (
          <span>{t('faces.onlyThisScreen')}</span>
        )}
      </div>

      {!packDir ? (
        <div className="flex flex-col items-start gap-2 rounded-md border border-dashed p-3 text-sm">
          <p className="text-muted-foreground">{t('faces.setPackFirst')}</p>
          <Button variant="outline" size="sm" asChild>
            <Link to="/settings">
              <Settings /> {t('faces.goToSettings')}
            </Link>
          </Button>
        </div>
      ) : packQuery.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" /> {t('faces.opening')}
        </p>
      ) : packQuery.error ? (
        <div className="flex flex-col items-start gap-2 rounded-md border border-destructive/40 p-3 text-sm">
          <p className="text-destructive">
            {packQuery.error instanceof ApiError ? packQuery.error.message : t('faces.openFailed')}
          </p>
          {!otherDir && (
            <Button variant="outline" size="sm" asChild>
              <Link to="/settings">
                <Settings /> {t('faces.checkSettings')}
              </Link>
            </Button>
          )}
        </div>
      ) : null}

      {pack && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm">
              <span className="font-medium">{pack.name}</span> <span className="text-muted-foreground">· {t('faces.count', { count: pack.faces.length })}</span>
            </p>
            <div className="relative w-44">
              <Search className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t('faces.filter')} className="h-7 pl-7 text-xs" />
            </div>
          </div>
          <div className="grid max-h-[26rem] grid-cols-[repeat(auto-fill,minmax(5.5rem,1fr))] gap-1.5 overflow-y-auto rounded-md border bg-muted/30 p-1.5">
            {faces.map((f) => {
              const selected = browsing?.face.id === f.id && browsing.folder === pack.folder
              const current = player.face?.source_id === f.id
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => onBrowse(selected ? null : { folder: pack.folder, face: f })}
                  className={cn(
                    'relative flex flex-col items-center rounded-md border bg-background p-1 text-xs hover:border-primary',
                    selected && 'border-primary ring-2 ring-primary/40',
                  )}
                  title={[
                    f.player ? [f.player.name, f.player.club, f.player.nationality].filter(Boolean).join(' · ') : t('faces.unknownPlayer'),
                    t('faces.face', { id: f.id }) + (f.hair ? '' : ` ${t('faces.noHair')}`),
                  ].join('\n')}
                >
                  <img src={faceThumbUrl({ folder: pack.folder, face: f.id })} alt="" loading="lazy" className="aspect-square w-full object-contain" />
                  <span className="w-full truncate text-center text-[11px] leading-tight">{f.player?.name ?? '—'}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{f.id}</span>
                  {current && <Check className="absolute top-1 left-1 size-3.5 text-primary" />}
                </button>
              )
            })}
            {!faces.length && <p className="col-span-full p-4 text-center text-xs text-muted-foreground">{t('faces.none')}</p>}
          </div>
        </div>
      )}

      {browsing && (
        <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/5 p-2 text-sm">
          <p className="min-w-0 flex-1">
            {t('faces.viewing')}{' '}
            <span className="font-medium">
              {browsing.face.player ? `${browsing.face.player.name} (${browsing.face.id})` : browsing.face.id}
            </span>{' '}
            {t('faces.viewingRest')}
          </p>
          <Button size="sm" onClick={() => void pick()} disabled={picking}>
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
