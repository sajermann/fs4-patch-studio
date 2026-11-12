import { SingleZipImport } from '@/components/common/share'
import { EntryDates } from '@/components/common/dates'
import { Download, ImageOff, LoaderCircle, RotateCcw, Trash2, Upload, UserMinus, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Glove } from '@/api/types'
import { GloveThumb } from '@/components/common/GloveThumb'
import { CreditsUrlInput } from '@/components/common/CreditsUrlInput'
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
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useGoBack } from '@/lib/back'
import { admitImported, gloveKey, gloveName, glovePath, useGloveSlots, wearers } from '@/lib/gloves'
import { keyOfPath, playerName, playerPath, playerRef } from '@/lib/players'
import { newUid, useIssues, useProject, useWasEdited } from '@/state/project'
import { useOriginalGloves } from '@/state/queries'

const GlovePreview = lazy(() => import('@/components/common/GlovePreview'))

/** The glove an address names: a new one by uid, one of the game's by its code (its entry loaded from the game the
 * first time, shown as the game's until something changes). */
function useGloveOfPath(param: string | undefined) {
  const { t } = useI18n()
  const { loaded, draft, openOriginal } = useProject()
  const key = keyOfPath(param)
  const gloves = draft.gloves ?? []
  const entry = typeof key === 'number' ? gloves.find((g) => g.original_id === key) : gloves.find((g) => g.uid === key)
  const [failed, setFailed] = useState<number>()
  const absent = loaded && typeof key === 'number' && !entry
  useEffect(() => {
    if (!absent || typeof key !== 'number') return
    let live = true
    api
      .editOriginalGlove(key, newUid())
      .then((glove) => live && openOriginal({ glove }))
      .catch((e) => {
        if (!live) return
        setFailed(key)
        toast.error(e instanceof ApiError ? e.message : t('gloves.editOriginalFailed'))
      })
    return () => {
      live = false
    }
    // once per absent code
  }, [absent, key])
  return { entry, loading: !entry && (!loaded || (absent && failed !== key)) }
}

/** A file field: what is there and a button to send another one. */
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
        <span className={has ? 'text-sm' : 'text-sm text-muted-foreground'}>{has ? t('gloves.fileSent') : (fallback ?? t('gloves.fileMissing'))}</span>
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
          {busy ? <LoaderCircle className="animate-spin" /> : <Upload />} {has ? t('gloves.fileReplace') : t('gloves.fileSend')}
        </Button>
        {extra}
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <FieldIssues issues={issues} />
    </div>
  )
}

export function GloveEditPage() {
  const { t } = useI18n()
  const { uid: param } = useParams()
  const { draft, dirty, updateGlove, removeGloves, takeOffGlove, save } = useProject()
  const { entry: glove, loading } = useGloveOfPath(param)
  const back = useBack({ to: '/gloves', label: t('nav.gloves') })
  const goBack = useGoBack()
  const from = useFrom(glove ? gloveName(glove, t('gloves.new')) : t('nav.gloves')) // a player's "←" comes back here
  const edited = useWasEdited(glove?.uid)
  const slots = useGloveSlots(glove?.uid)
  const gameGloves = useOriginalGloves().data
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [takingOff, setTakingOff] = useState<string[] | null>(null) // players to take the glove off, asking first
  const [busy, setBusy] = useState(false)

  if (!glove) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {loading ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <p className="text-muted-foreground">{t('gloves.notFound')}</p>}
      </div>
    )
  }

  const original = glove.original_id != null
  const set = (patch: Partial<Glove>) => updateGlove(glove.uid, patch)
  const name = gloveName(glove, t('gloves.new'))
  const ref = original ? glove.original_id! : glove.uid
  const users = wearers(draft, original ? { original_id: glove.original_id! } : glove)
  const takeOffNames = (takingOff ?? []).map((uid) => users.find((u) => u.uid === uid)).filter((u) => !!u)
  const gamePlayers = original ? gameGloves?.find((g) => g.code === glove.original_id)?.players : undefined

  const uploadTexture = async (file: File) => {
    try {
      set({ texture: (await api.uploadGloveFile(file)).path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('gloves.uploadFailed'))
    }
  }
  const uploadThumb = async (file: File) => {
    try {
      set({ thumbnail: (await api.uploadGloveThumbnail(file)).path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('gloves.uploadFailed'))
    }
  }

  const download = async () => {
    setBusy(true)
    try {
      if (dirty) await save()
      const { name: fileName, blob } = await api.exportGloves([glove.uid])
      saveBlob(fileName, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('gloves.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const previewSource = glove.texture
    ? ({ kind: 'project', texture: glove.texture } as const)
    : original
      ? ({ kind: 'game', code: glove.original_id! } as const)
      : null

  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <GloveThumb glove={glove} className="size-12" />
          <div>
            <h1 className="text-2xl font-semibold break-words">{name}</h1>
            <EntryDates entry={glove} />
          </div>
          {original && <OriginalBadge entry={glove.uid} />}
          {!original && glove.hidden && <OutOfPatchBadge alert />}
        </div>
        <div className="flex flex-col items-end justify-between">
          <div className="flex flex-wrap gap-2">
            {!original && (
              <HideButton
                variant="outline"
                hidden={!!glove.hidden}
                onToggle={() => {
                  if (glove.hidden && !slots.free) {
                    toast.error(t('gloves.slotsFull', { total: slots.total }))
                    return
                  }
                  set({ hidden: !glove.hidden })
                }}
                hideHint={t('gloves.hideHint')}
                showHint={t('gloves.showHint')}
              />
            )}
            <SingleZipImport
              kind="gloves"
              entry={glove}
              read={async (file) => {
                const r = await api.importGloves(file)
                return { items: r.gloves, problems: r.problems }
              }}
              admit={(item) => admitImported([item as Glove], slots.free)[0]}
              pathOf={(e) => glovePath(gloveKey(e as Glove))}
              label={t('gloves.uploadZip')}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={busy || !glove.texture}
              title={glove.texture ? t('gloves.downloadHint') : t('gloves.downloadNeedsFile')}
              onClick={() => void download()}
            >
              <Download /> {t('gloves.download')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              title={original ? t(edited ? 'gloves.restoreOriginalHint' : 'common.unchangedHint') : undefined}
              disabled={original && !edited}
              onClick={() => setDeleteOpen(true)}
            >
              {original ? <RotateCcw /> : <Trash2 />} {original ? t('teamEdit.restoreOriginal') : t('gloves.delete')}
            </Button>
          </div>
          <EntityIssues uid={glove.uid} />
        </div>
      </div>

      <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
        <div className="min-w-0 space-y-4 xl:flex-1">
          <Card>
            <CardContent className="grid gap-4 pt-6">
              <Field label={t('gloves.name')} entity={glove.uid} field="name">
                <Input value={glove.name} autoFocus={!glove.name} onChange={(e) => set({ name: e.target.value })} />
              </Field>
              <Field label={t('gloves.credits')} hint={t('gloves.creditsHint')} entity={glove.uid} field="credits">
                <Input value={glove.credits ?? ''} onChange={(e) => set({ credits: e.target.value || undefined })} />
              </Field>
              <Field label={t('credits.link')} hint={t('credits.linkHint')} entity={glove.uid} field="credits_url">
                <CreditsUrlInput key={glove.uid} value={glove.credits_url} onChange={(url) => set({ credits_url: url })} />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('gloves.files')}</CardTitle>
              <CardDescription>{original ? t('gloves.filesOriginalDescription') : t('gloves.filesDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <FileField
                label={t('gloves.texture')}
                hint={t('gloves.textureHint')}
                accept=".rx3"
                has={!!glove.texture}
                fallback={original ? t('gloves.gameFile') : undefined}
                entity={glove.uid}
                field="texture"
                onPick={uploadTexture}
                extra={
                  original &&
                  glove.texture && (
                    <Button variant="ghost" size="sm" onClick={() => set({ texture: undefined })}>
                      <RotateCcw /> {t('gloves.gameFileBack')}
                    </Button>
                  )
                }
              />
              <FileField
                label={t('gloves.thumbnail')}
                hint={t('gloves.thumbnailHint')}
                accept=".png,.jpg,.jpeg,.webp"
                has={!!glove.thumbnail}
                fallback={t('gloves.thumbnailAuto')}
                entity={glove.uid}
                field="thumbnail"
                onPick={uploadThumb}
                extra={
                  glove.thumbnail && (
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
              <CardTitle>{t('gloves.wearers')}</CardTitle>
              <CardDescription>
                {original ? t('gloves.wearersOriginal', { count: gamePlayers ?? 0 }) : t('gloves.wearersDescription')}
              </CardDescription>
              {users.length > 1 && (
                <CardAction>
                  <Button variant="outline" size="sm" onClick={() => setTakingOff(users.map((u) => u.uid))}>
                    <UserMinus /> {t('gloves.takeOffAll')}
                  </Button>
                </CardAction>
              )}
            </CardHeader>
            <CardContent>
              {users.length ? (
                <ul className="space-y-1 text-sm">
                  {users.map((player) => (
                    <li key={player.uid} className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                        title={t('gloves.takeOff')}
                        aria-label={t('gloves.takeOff')}
                        onClick={() => setTakingOff([player.uid])}
                      >
                        <X />
                      </Button>
                      <Link className="min-w-0 truncate underline-offset-2 hover:underline" to={playerPath(playerRef(player))} state={from.state}>
                        {playerName(player, t('common.unnamed'))}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">{t('gloves.noWearers')}</p>
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
              <GlovePreview source={previewSource} />
            </Suspense>
          </div>
          <p className="cursor-help px-4 pb-3 text-center text-xs text-muted-foreground" title={t('preview.controls')}>
            {t('gloves.previewLabel')}
          </p>
        </Card>
      </div>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {original ? t('teamEdit.restoreOriginalTitle', { name }) : t('teamEdit.deleteTitle', { name })}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                {original ? (
                  <p>{t('gloves.restoreOriginalDescription')}</p>
                ) : (
                  <>
                    {users.length > 0 && (
                      <>
                        <p>{t('gloves.deleteWorn')}</p>
                        <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                          {users.map((player) => (
                            <li key={player.uid} className="text-foreground">
                              {playerName(player, t('common.unnamed'))}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    <p>{t('gloves.deleteDescription')}</p>
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removeGloves([glove.uid]) // also takes it off its players
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
                ? t('gloves.takeOffTitle', { name: playerName(takeOffNames[0], t('common.unnamed')) })
                : t('gloves.takeOffAllTitle', { count: takeOffNames.length })}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>{t('gloves.takeOffDescription')}</p>
                {takeOffNames.length > 1 && (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {takeOffNames.map((player) => (
                      <li key={player.uid} className="text-foreground">
                        {playerName(player, t('common.unnamed'))}
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
                takeOffGlove(ref, takingOff ?? [])
                setTakingOff(null)
              }}
            >
              {t('gloves.takeOffConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
