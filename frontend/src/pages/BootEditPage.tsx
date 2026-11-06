import { Download, FileUp, ImageOff, LoaderCircle, RotateCcw, Trash2, Upload, UserMinus, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Boot, ShoeSurface } from '@/api/types'
import { BootThumb } from '@/components/common/BootThumb'
import { EntityIssues, Field, FieldIssues, OriginalBadge } from '@/components/common/form'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
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
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useGoBack } from '@/lib/back'
import { bootName, streetCode, SURFACE_LABELS, useStreetSlots, wearers } from '@/lib/boots'
import { keyOfPath, playerName, playerPath, playerRef } from '@/lib/players'
import { newUid, useIssues, useProject, useWasEdited } from '@/state/project'
import { useOriginalBoots } from '@/state/queries'

const BootPreview = lazy(() => import('@/components/common/BootPreview'))

/** The boot an address names: a new one by uid, one of the game's by its code (its entry loaded from the game the
 * first time, shown as the game's until something changes). */
function useBootOfPath(param: string | undefined) {
  const { t } = useI18n()
  const { loaded, draft, openOriginal } = useProject()
  const key = keyOfPath(param)
  const boots = draft.boots ?? []
  const entry = typeof key === 'number' ? boots.find((b) => b.original_id === key) : boots.find((b) => b.uid === key)
  const [failed, setFailed] = useState<number>()
  const absent = loaded && typeof key === 'number' && !entry
  useEffect(() => {
    if (!absent || typeof key !== 'number') return
    let live = true
    api
      .editOriginalBoot(key, newUid())
      .then((boot) => live && openOriginal({ boot }))
      .catch((e) => {
        if (!live) return
        setFailed(key)
        toast.error(e instanceof ApiError ? e.message : t('boots.editOriginalFailed'))
      })
    return () => {
      live = false
    }
    // once per absent code
  }, [absent, key])
  return { entry, loading: !entry && (!loaded || (absent && failed !== key)) }
}

/** A pack file field: what is there and a button to send another one. */
function FileField({
  label,
  hint,
  accept,
  has,
  fallback,
  entity,
  field,
  onPick,
  extra,
}: {
  label: string
  hint: string
  accept: string
  has: boolean
  fallback?: string
  entity: string
  field: string
  onPick: (file: File) => Promise<void>
  extra?: ReactNode
}) {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const issues = useIssues(entity, field)
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <span className={has ? 'text-sm' : 'text-sm text-muted-foreground'}>{has ? t('boots.fileSent') : (fallback ?? t('boots.fileMissing'))}</span>
        <input
          ref={input}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = ''
            if (!file) return
            setBusy(true)
            onPick(file).finally(() => setBusy(false))
          }}
        />
        <Button variant="outline" size="sm" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? <LoaderCircle className="animate-spin" /> : <Upload />} {has ? t('boots.fileReplace') : t('boots.fileSend')}
        </Button>
        {extra}
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <FieldIssues issues={issues} />
    </div>
  )
}

export function BootEditPage() {
  const { t } = useI18n()
  const { uid: param } = useParams()
  const { draft, dirty, updateBoot, removeBoots, takeOffBoot, save } = useProject()
  const { entry: boot, loading } = useBootOfPath(param)
  const back = useBack({ to: '/boots', label: t('nav.boots') })
  const goBack = useGoBack()
  const from = useFrom(boot ? bootName(boot, t('boots.new')) : t('nav.boots')) // a player's "←" comes back here
  const edited = useWasEdited(boot?.uid)
  const slots = useStreetSlots(boot?.uid)
  const gameBoots = useOriginalBoots().data
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [streetBlocked, setStreetBlocked] = useState(false)
  const [takingOff, setTakingOff] = useState<string[] | null>(null) // players to take the boot off, asking first
  const [busy, setBusy] = useState(false)
  const zipInput = useRef<HTMLInputElement>(null)

  if (!boot) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {loading ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <p className="text-muted-foreground">{t('boots.notFound')}</p>}
      </div>
    )
  }

  const original = boot.original_id != null
  const set = (patch: Partial<Boot>) => updateBoot(boot.uid, patch)
  const name = bootName(boot, t('boots.new'))
  const hasFiles = !!(boot.mesh && boot.texture)
  const users = wearers(draft, original ? { original_id: boot.original_id! } : boot)
  const onStreet = users.filter((u) => u.surfaces.includes('street'))
  const takeOffNames = (takingOff ?? []).map((uid) => users.find((u) => u.player.uid === uid)).filter((u) => !!u)
  const surfacesText = (surfaces: ShoeSurface[]) => surfaces.map((s) => t(SURFACE_LABELS[s])).join(', ')
  const gamePlayers = original ? gameBoots?.find((b) => b.code === boot.original_id)?.players : undefined
  const street = original ? streetCode(boot.original_id!) : !!boot.street

  const upload = (kind: 'mesh' | 'texture') => async (file: File) => {
    try {
      set({ [kind]: (await api.uploadBootFile(kind, file)).path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('boots.uploadFailed'))
    }
  }
  const uploadThumb = async (file: File) => {
    try {
      set({ thumbnail: (await api.uploadBootThumbnail(file)).path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('boots.uploadFailed'))
    }
  }

  const setStreet = (on: boolean) => {
    if (on && !boot.hidden && !slots.free) {
      toast.error(t('boots.streetFull', { total: slots.total }))
      return
    }
    if (!on && onStreet.length) {
      setStreetBlocked(true)
      return
    }
    set({ street: on })
  }

  const importOne = async (file: File) => {
    setBusy(true)
    try {
      const r = await api.importBoots(file)
      if (r.boots.length !== 1) {
        toast.error(t('boots.zipHasMany', { count: r.boots.length }))
        return
      }
      const got = r.boots[0]
      const patch: Partial<Boot> = { name: got.name, credits: got.credits, mesh: got.mesh, texture: got.texture, thumbnail: got.thumbnail }
      if (!original) {
        const wantsStreet = !!got.street
        patch.street = wantsStreet && (boot.hidden || slots.free > 0 || !!boot.street)
        if (wantsStreet && !patch.street) toast.warning(t('boots.streetFull', { total: slots.total }))
      }
      set(patch)
      r.problems.forEach((p) => toast.warning(p.message))
      toast.success(t('boots.zipFilled'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('boots.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const download = async () => {
    setBusy(true)
    try {
      if (dirty) await save()
      const { name: fileName, blob } = await api.exportBoots([boot.uid])
      saveBlob(fileName, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('boots.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const previewSource = hasFiles
    ? ({ kind: 'project', mesh: boot.mesh!, texture: boot.texture! } as const)
    : original
      ? ({ kind: 'game', code: boot.original_id! } as const)
      : null

  return (
    <div className="max-w-7xl space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <BootThumb boot={boot} className="h-10 w-20" />
          <h1 className="text-2xl font-semibold">{name}</h1>
          {original && <OriginalBadge entry={boot.uid} />}
          {!original && boot.hidden && <OutOfPatchBadge alert />}
          <EntityIssues uid={boot.uid} />
        </div>
        <div className="flex flex-wrap gap-2">
          {!original && (
            <HideButton
              variant="outline"
              hidden={!!boot.hidden}
              onToggle={() => {
                if (boot.hidden && boot.street && !slots.free) {
                  toast.error(t('boots.streetFull', { total: slots.total }))
                  return
                }
                set({ hidden: !boot.hidden })
              }}
              hideHint={t('boots.hideHint')}
              showHint={t('boots.showHint')}
            />
          )}
          <input
            ref={zipInput}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              e.target.value = ''
              if (file) void importOne(file)
            }}
          />
          <Button variant="outline" size="sm" disabled={busy} title={t('boots.uploadZipHint')} onClick={() => zipInput.current?.click()}>
            <FileUp /> {t('boots.uploadZip')}
          </Button>
          <Button variant="outline" size="sm" disabled={busy || !hasFiles} title={hasFiles ? t('boots.downloadHint') : t('boots.downloadNeedsFiles')} onClick={() => void download()}>
            <Download /> {t('boots.download')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            title={original ? t(edited ? 'boots.restoreOriginalHint' : 'common.unchangedHint') : undefined}
            disabled={original && !edited}
            onClick={() => setDeleteOpen(true)}
          >
            {original ? <RotateCcw /> : <Trash2 />} {original ? t('teamEdit.restoreOriginal') : t('boots.delete')}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
        <div className="space-y-4 xl:w-[30rem] xl:shrink-0">
          <Card>
            <CardContent className="grid gap-4 pt-6">
              <Field label={t('boots.name')} entity={boot.uid} field="name">
                <Input value={boot.name} autoFocus={!boot.name} onChange={(e) => set({ name: e.target.value })} />
              </Field>
              <Field label={t('boots.credits')} hint={t('boots.creditsHint')} entity={boot.uid} field="credits">
                <Input value={boot.credits ?? ''} onChange={(e) => set({ credits: e.target.value || undefined })} />
              </Field>
              {original ? (
                <div className="space-y-1">
                  <Label>{t('boots.street')}</Label>
                  <p className="text-sm text-muted-foreground">
                    {street ? t('boots.streetOriginalYes', { code: boot.original_id! }) : t('boots.streetOriginalNo', { code: boot.original_id! })}
                  </p>
                </div>
              ) : (
                <Field label={t('boots.street')} entity={boot.uid} field="street">
                  <label className="flex items-start gap-2 text-sm">
                    <Switch checked={!!boot.street} onCheckedChange={setStreet} className="mt-0.5" />
                    <span>
                      {t('boots.streetLabel')}
                      <span className="block text-xs text-muted-foreground">{t('boots.streetHint', { free: slots.free, total: slots.total })}</span>
                    </span>
                  </label>
                </Field>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('boots.files')}</CardTitle>
              <CardDescription>{original ? t('boots.filesOriginalDescription') : t('boots.filesDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <FileField
                label={t('boots.mesh')}
                hint={t('boots.meshHint')}
                accept=".rx3"
                has={!!boot.mesh}
                fallback={original ? t('boots.gameFile') : undefined}
                entity={boot.uid}
                field="mesh"
                onPick={upload('mesh')}
              />
              <FileField
                label={t('boots.texture')}
                hint={t('boots.textureHint')}
                accept=".rx3"
                has={!!boot.texture}
                fallback={original ? t('boots.gameFile') : undefined}
                entity={boot.uid}
                field="texture"
                onPick={upload('texture')}
              />
              {original && (boot.mesh || boot.texture) && (
                <Button variant="ghost" size="sm" className="w-fit" onClick={() => set({ mesh: undefined, texture: undefined })}>
                  <RotateCcw /> {t('boots.gameFilesBack')}
                </Button>
              )}
              <FileField
                label={t('boots.thumbnail')}
                hint={t('boots.thumbnailHint')}
                accept=".png,.jpg,.jpeg,.webp"
                has={!!boot.thumbnail}
                fallback={t('boots.thumbnailAuto')}
                entity={boot.uid}
                field="thumbnail"
                onPick={uploadThumb}
                extra={
                  boot.thumbnail && (
                    <Button variant="ghost" size="sm" onClick={() => set({ thumbnail: undefined })}>
                      <ImageOff /> {t('common.remove')}
                    </Button>
                  )
                }
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('boots.wearers')}</CardTitle>
              <CardDescription>
                {original ? t('boots.wearersOriginal', { count: gamePlayers ?? 0 }) : t('boots.wearersDescription')}
              </CardDescription>
              {!original && users.length > 1 && (
                <CardAction>
                  <Button variant="outline" size="sm" onClick={() => setTakingOff(users.map((u) => u.player.uid))}>
                    <UserMinus /> {t('boots.takeOffAll')}
                  </Button>
                </CardAction>
              )}
            </CardHeader>
            <CardContent>
              {users.length ? (
                <ul className="space-y-1 text-sm">
                  {users.map(({ player, surfaces }) => (
                    <li key={player.uid} className="flex items-center gap-2">
                      {/* the game's boots are taken off in the player's Accessories tab */}
                      {!original && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                          title={t('boots.takeOff')}
                          aria-label={t('boots.takeOff')}
                          onClick={() => setTakingOff([player.uid])}
                        >
                          <X />
                        </Button>
                      )}
                      <span className="min-w-0 truncate">
                        <Link className="underline-offset-2 hover:underline" to={playerPath(playerRef(player))} state={from.state}>
                          {playerName(player, t('common.unnamed'))}
                        </Link>
                        <span className="text-muted-foreground"> — {surfacesText(surfaces)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">{t('boots.noWearers')}</p>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="order-first h-fit min-w-0 flex-1 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-none">
          <div className="aspect-[4/3] max-h-[70vh] w-full bg-gradient-to-b from-muted to-background">
            <Suspense
              fallback={
                <div className="flex size-full items-center justify-center text-muted-foreground">
                  <LoaderCircle className="size-6 animate-spin" />
                </div>
              }
            >
              <BootPreview source={previewSource} />
            </Suspense>
          </div>
          <p className="cursor-help px-4 pb-3 text-center text-xs text-muted-foreground" title={t('preview.controls')}>
            {t('boots.previewLabel')}
          </p>
        </Card>
      </div>

      <AlertDialog open={streetBlocked} onOpenChange={setStreetBlocked}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('boots.streetInUseTitle')}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>{t('boots.streetInUse')}</p>
                <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                  {onStreet.map(({ player }) => (
                    <li key={player.uid} className="text-foreground">
                      {playerName(player, t('common.unnamed'))}
                    </li>
                  ))}
                </ul>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.close')}</AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {original ? t('teamEdit.restoreOriginalTitle', { name }) : t('teamEdit.deleteTitle', { name })}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                {original ? (
                  <p>{t('boots.restoreOriginalDescription')}</p>
                ) : (
                  <>
                    {users.length > 0 && (
                      <>
                        <p>{t('boots.deleteWorn')}</p>
                        <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                          {users.map(({ player, surfaces }) => (
                            <li key={player.uid} className="text-foreground">
                              {playerName(player, t('common.unnamed'))} ({surfacesText(surfaces)})
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    <p>{t('boots.deleteDescription')}</p>
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removeBoots([boot.uid]) // also takes it off its players
                if (!original) goBack(back) // restored: the page stays and loads it again from the game
              }}
            >
              {original ? t('teamEdit.restoreOriginal') : t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={takingOff !== null} onOpenChange={(open) => !open && setTakingOff(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {takeOffNames.length === 1
                ? t('boots.takeOffTitle', { name: playerName(takeOffNames[0].player, t('common.unnamed')) })
                : t('boots.takeOffAllTitle', { count: takeOffNames.length })}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>{t('boots.takeOffDescription')}</p>
                {takeOffNames.length > 1 && (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {takeOffNames.map(({ player, surfaces }) => (
                      <li key={player.uid} className="text-foreground">
                        {playerName(player, t('common.unnamed'))} ({surfacesText(surfaces)})
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                takeOffBoot(boot.uid, takingOff ?? [])
                setTakingOff(null)
              }}
            >
              {t('boots.takeOffConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
