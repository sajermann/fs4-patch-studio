import { Download, FileUp, ImageOff, LoaderCircle, RotateCcw, Trash2, Upload, Undo2, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, saveBlob } from '@/api/client'
import type { Ball } from '@/api/types'
import { BallThumb } from '@/components/common/BallThumb'
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom, useGoBack } from '@/lib/back'
import { ballName, gameBallName, REGION_LABELS, stadiumsUsing, useBallSlots } from '@/lib/balls'
import { keyOfPath } from '@/lib/players'
import { stadiumPath } from '@/lib/stadiums'
import { newUid, useIssues, useProject, useWasEdited } from '@/state/project'
import { useOriginalBalls, useOriginalStadiums } from '@/state/queries'

const BallPreview = lazy(() => import('@/components/common/BallPreview'))

/** The ball an address names: a new one by uid, one of the game's by its id (its entry loaded from the game the
 * first time, shown as the game's until something changes). */
function useBallOfPath(param: string | undefined) {
  const { t } = useI18n()
  const { loaded, draft, openOriginal } = useProject()
  const key = keyOfPath(param)
  const balls = draft.balls ?? []
  const entry = typeof key === 'number' ? balls.find((b) => b.original_id === key) : balls.find((b) => b.uid === key)
  const [failed, setFailed] = useState<number>()
  const absent = loaded && typeof key === 'number' && !entry
  useEffect(() => {
    if (!absent || typeof key !== 'number') return
    let live = true
    api
      .editOriginalBall(key, newUid())
      .then((ball) => live && openOriginal({ ball }))
      .catch((e) => {
        if (!live) return
        setFailed(key)
        toast.error(e instanceof ApiError ? e.message : t('balls.editOriginalFailed'))
      })
    return () => {
      live = false
    }
    // once per absent id
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
        <span className={has ? 'text-sm' : 'text-sm text-muted-foreground'}>{has ? t('balls.fileSent') : (fallback ?? t('balls.fileMissing'))}</span>
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
          {busy ? <LoaderCircle className="animate-spin" /> : <Upload />} {has ? t('balls.fileReplace') : t('balls.fileSend')}
        </Button>
        {extra}
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <FieldIssues issues={issues} />
    </div>
  )
}

export function BallEditPage() {
  const { t } = useI18n()
  const { uid: param } = useParams()
  const { draft, dirty, updateBall, removeBalls, setStadiumBalls, save } = useProject()
  const { entry: ball, loading } = useBallOfPath(param)
  const back = useBack({ to: '/balls', label: t('nav.balls') })
  const goBack = useGoBack()
  const from = useFrom(ball ? ballName(ball, t('balls.new')) : t('nav.balls')) // a stadium's "←" comes back here
  const edited = useWasEdited(ball?.uid)
  const slots = useBallSlots(ball?.uid)
  const gameBalls = useOriginalBalls().data
  const stadiums = useOriginalStadiums().data ?? []
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [takingOff, setTakingOff] = useState<number[] | null>(null) // stadium rows to take the ball off, asking first
  const [busy, setBusy] = useState(false)
  const zipInput = useRef<HTMLInputElement>(null)

  if (!ball) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {loading ? <LoaderCircle className="size-5 animate-spin text-muted-foreground" /> : <p className="text-muted-foreground">{t('balls.notFound')}</p>}
      </div>
    )
  }

  const original = ball.original_id != null
  const set = (patch: Partial<Ball>) => updateBall(ball.uid, patch)
  const gameName = original
    ? gameBallName(
        gameBalls?.find((b) => b.id === ball.original_id),
        ball.original_id!,
        (id) => t('balls.gameName', { id }),
      )
    : undefined
  const name = ballName(ball, gameName ?? t('balls.new'))
  const users = stadiumsUsing(draft, stadiums, original ? { original_id: ball.original_id! } : ball)
  const pickedUsers = users.filter((u) => u.picked)
  const versionLabel = (region: number) => (REGION_LABELS[region] ? t(REGION_LABELS[region]) : undefined)
  const takeOffRows = users.filter((u) => (takingOff ?? []).includes(u.version.id))
  const hasFiles = !!(ball.mesh && ball.texture)

  const upload = (kind: 'mesh' | 'texture') => async (file: File) => {
    try {
      set({ [kind]: (await api.uploadBallFile(kind, file)).path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('balls.uploadFailed'))
    }
  }
  const uploadThumb = async (file: File) => {
    try {
      set({ thumbnail: (await api.uploadBallThumbnail(file)).path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('balls.uploadFailed'))
    }
  }

  const importOne = async (file: File) => {
    setBusy(true)
    try {
      const r = await api.importBalls(file)
      if (r.balls.length !== 1) {
        toast.error(t('balls.zipHasMany', { count: r.balls.length }))
        return
      }
      const got = r.balls[0]
      set({ name: got.name, credits: got.credits, mesh: got.mesh, texture: got.texture, thumbnail: got.thumbnail })
      r.problems.forEach((p) => toast.warning(p.message))
      toast.success(t('balls.zipFilled'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('balls.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const download = async () => {
    setBusy(true)
    try {
      if (dirty) await save()
      const { name: fileName, blob } = await api.exportBalls([ball.uid])
      saveBlob(fileName, blob)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('balls.downloadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const previewSource = hasFiles
    ? ({ kind: 'project', mesh: ball.mesh!, texture: ball.texture! } as const)
    : original
      ? ({ kind: 'game', id: ball.original_id! } as const)
      : null

  return (
    <div className="max-w-7xl space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <BallThumb ball={ball} className="size-12" />
          <h1 className="text-2xl font-semibold">{name}</h1>
          {original && <OriginalBadge entry={ball.uid} />}
          {!original && ball.hidden && <OutOfPatchBadge alert />}
          <EntityIssues uid={ball.uid} />
        </div>
        <div className="flex flex-wrap gap-2">
          {!original && (
            <HideButton
              variant="outline"
              hidden={!!ball.hidden}
              onToggle={() => {
                if (ball.hidden && !slots.free) {
                  toast.error(t('balls.slotsFull', { total: slots.total }))
                  return
                }
                set({ hidden: !ball.hidden })
              }}
              hideHint={t('balls.hideHint')}
              showHint={t('balls.showHint')}
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
          <Button variant="outline" size="sm" disabled={busy} title={t('balls.uploadZipHint')} onClick={() => zipInput.current?.click()}>
            <FileUp /> {t('balls.uploadZip')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={busy || !hasFiles}
            title={hasFiles ? t('balls.downloadHint') : t('balls.downloadNeedsFiles')}
            onClick={() => void download()}
          >
            <Download /> {t('balls.download')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            title={original ? t(edited ? 'balls.restoreOriginalHint' : 'common.unchangedHint') : undefined}
            disabled={original && !edited}
            onClick={() => setDeleteOpen(true)}
          >
            {original ? <RotateCcw /> : <Trash2 />} {original ? t('teamEdit.restoreOriginal') : t('balls.delete')}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
        <div className="space-y-4 xl:w-[30rem] xl:shrink-0">
          <Card>
            <CardContent className="grid gap-4 pt-6">
              <Field label={t('balls.name')} entity={ball.uid} field="name">
                <Input value={ball.name} autoFocus={!ball.name} onChange={(e) => set({ name: e.target.value })} />
              </Field>
              <Field label={t('balls.credits')} hint={t('balls.creditsHint')} entity={ball.uid} field="credits">
                <Input value={ball.credits ?? ''} onChange={(e) => set({ credits: e.target.value || undefined })} />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('balls.files')}</CardTitle>
              <CardDescription>{original ? t('balls.filesOriginalDescription') : t('balls.filesDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <FileField
                label={t('balls.mesh')}
                hint={t('balls.meshHint')}
                accept=".rx3"
                has={!!ball.mesh}
                fallback={original ? t('balls.gameFile') : undefined}
                entity={ball.uid}
                field="mesh"
                onPick={upload('mesh')}
              />
              <FileField
                label={t('balls.texture')}
                hint={t('balls.textureHint')}
                accept=".rx3"
                has={!!ball.texture}
                fallback={original ? t('balls.gameFile') : undefined}
                entity={ball.uid}
                field="texture"
                onPick={upload('texture')}
              />
              {original && (ball.mesh || ball.texture) && (
                <Button variant="ghost" size="sm" className="w-fit" onClick={() => set({ mesh: undefined, texture: undefined })}>
                  <RotateCcw /> {t('balls.gameFilesBack')}
                </Button>
              )}
              <FileField
                label={t('balls.thumbnail')}
                hint={t('balls.thumbnailHint')}
                accept=".png,.jpg,.jpeg,.webp"
                has={!!ball.thumbnail}
                fallback={t('balls.thumbnailAuto')}
                entity={ball.uid}
                field="thumbnail"
                onPick={uploadThumb}
                extra={
                  ball.thumbnail && (
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
              <CardTitle>{t('balls.users')}</CardTitle>
              <CardDescription>{original ? t('balls.usersOriginal') : t('balls.usersDescription')}</CardDescription>
              {pickedUsers.length > 1 && (
                <CardAction>
                  <Button variant="outline" size="sm" onClick={() => setTakingOff(pickedUsers.map((u) => u.version.id))}>
                    <Undo2 /> {t('balls.takeOffAll')}
                  </Button>
                </CardAction>
              )}
            </CardHeader>
            <CardContent>
              {users.length ? (
                <ul className="space-y-1 text-sm">
                  {users.map(({ stadium, version, picked }) => (
                    <li key={version.id} className="flex items-center gap-2">
                      {picked ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                          title={t('balls.takeOff')}
                          aria-label={t('balls.takeOff')}
                          onClick={() => setTakingOff([version.id])}
                        >
                          <X />
                        </Button>
                      ) : (
                        <span className="size-7 shrink-0" />
                      )}
                      <Link className="min-w-0 truncate underline-offset-2 hover:underline" to={stadiumPath(stadium.id)} state={from.state}>
                        {stadium.name}
                      </Link>
                      {versionLabel(version.region) && <span className="text-xs text-muted-foreground">{versionLabel(version.region)}</span>}
                      {!picked && (
                        <Badge variant="outline" className="font-normal">
                          {t('balls.gameChoice')}
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">{t('balls.noUsers')}</p>
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
              <BallPreview source={previewSource} />
            </Suspense>
          </div>
          <p className="cursor-help px-4 pb-3 text-center text-xs text-muted-foreground" title={t('preview.controls')}>
            {t('balls.previewLabel')}
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
                  <p>{t('balls.restoreOriginalDescription')}</p>
                ) : (
                  <>
                    {pickedUsers.length > 0 && (
                      <>
                        <p>{t('balls.deleteUsed')}</p>
                        <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                          {pickedUsers.map(({ stadium, version }) => (
                            <li key={version.id} className="text-foreground">
                              {stadium.name}
                              {versionLabel(version.region) && ` (${versionLabel(version.region)})`}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    <p>{t('balls.deleteDescription')}</p>
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removeBalls([ball.uid]) // also takes it off its stadiums
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
              {takeOffRows.length === 1
                ? t('balls.takeOffTitle', { name: takeOffRows[0].stadium.name })
                : t('balls.takeOffAllTitle', { count: takeOffRows.length })}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>{t('balls.takeOffDescription')}</p>
                {takeOffRows.length > 1 && (
                  <ul className="max-h-60 space-y-1 overflow-auto text-sm">
                    {takeOffRows.map(({ stadium, version }) => (
                      <li key={version.id} className="text-foreground">
                        {stadium.name}
                        {versionLabel(version.region) && ` (${versionLabel(version.region)})`}
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
                setStadiumBalls(
                  takeOffRows.map((u) => ({ id: u.version.id, original: u.version.ball })),
                  null,
                )
                setTakingOff(null)
              }}
            >
              {t('balls.takeOffConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
