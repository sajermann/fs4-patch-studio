import { AlertTriangle, Copy, Info, LoaderCircle, Lock, LockOpen, Repeat } from 'lucide-react'
import { lazy, Suspense, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { Ball, StadiumVersion } from '@/api/types'
import { BallThumb } from '@/components/common/BallThumb'
import type { BallSource } from '@/components/common/BallPreview'
import { matches } from '@/components/common/list'
import { PickerDialog, type PickerGroup } from '@/components/common/PickerDialog'
import { CreditsLink } from '@/components/common/CreditsLink'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom } from '@/lib/back'
import { ballKey, ballName, ballPath, gameBallName, pickedBall, REGION_LABELS } from '@/lib/balls'
import { useOriginalChanges } from '@/lib/originals'
import { filterLabel, GAME_MODES, goalLabel, menuVersion, modesOf, SURFACE_LABELS, TIME_LABELS } from '@/lib/stadiums'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useCatalog, useOriginalBalls, useOriginalStadiums } from '@/state/queries'

const BallPreview = lazy(() => import('@/components/common/BallPreview'))

type PickKey = string // 'p:<uid>' (project ball) | 'g:<id>' (game ball)

/** What a stadium row shows as its ball: a ball of the project, or one of the game's (maybe edited in the project). */
type Shown = { kind: 'project'; ball: Ball } | { kind: 'game'; id: number; edited?: Ball }

function Info2({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm">{children}</p>
    </div>
  )
}

export function StadiumPage() {
  const { t } = useI18n()
  const { id: param } = useParams()
  const { draft, setStadiumBalls } = useProject()
  const stadiums = useOriginalStadiums().data
  const gameBalls = useOriginalBalls().data ?? []
  const filters = useCatalog().data?.stadium_filters ?? []
  const { stadiumLocked, setStadiumLocked } = useOriginalChanges()
  const back = useBack({ to: '/stadiums', label: t('nav.stadiums') })
  const stadium = stadiums?.find((s) => s.id === Number(param) || s.versions.some((v) => v.id === Number(param)))
  const from = useFrom(stadium?.name ?? t('nav.stadiums')) // a ball's "←" comes back here
  const [selected, setSelected] = useState<number>() // the row shown in the preview
  const [picking, setPicking] = useState<StadiumVersion[] | null>(null) // rows getting a ball, asking which
  const [query, setQuery] = useState('')

  if (!stadium) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {stadiums === undefined ? (
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <p className="text-muted-foreground">{t('stadium.notFound')}</p>
        )}
      </div>
    )
  }

  const balls = draft.balls ?? []
  const picked = draft.originals?.stadium_balls ?? {}
  const locked = stadiumLocked(stadium)
  const many = stadium.versions.length > 1
  const gameName = (id: number) => gameBallName(gameBalls.find((b) => b.id === id), id, (n) => t('balls.gameName', { id: n }))

  const shownOf = (v: StadiumVersion): Shown => {
    const ref = pickedBall(draft, v)
    if (typeof ref === 'string') {
      const own = balls.find((b) => b.uid === ref && b.original_id == null)
      if (own && !own.hidden) return { kind: 'project', ball: own }
      return { kind: 'game', id: v.ball, edited: balls.find((b) => b.original_id === v.ball) } // hidden: the game's stays
    }
    return { kind: 'game', id: ref, edited: balls.find((b) => b.original_id === ref) }
  }
  const nameOf = (s: Shown) =>
    s.kind === 'project' ? ballName(s.ball, t('common.unnamed')) : s.edited?.name.trim() ? ballName(s.edited, '') : gameName(s.id)
  const hiddenPick = (v: StadiumVersion) => {
    const ref = picked[v.id]
    return typeof ref === 'string' ? balls.find((b) => b.uid === ref && b.hidden) : undefined
  }

  const current = stadium.versions.find((v) => v.id === selected) ?? menuVersion(stadium)
  const shown = shownOf(current)
  const source: BallSource =
    shown.kind === 'project'
      ? { kind: 'project', mesh: shown.ball.mesh!, texture: shown.ball.texture! }
      : shown.edited?.mesh && shown.edited.texture
        ? { kind: 'project', mesh: shown.edited.mesh, texture: shown.edited.texture }
        : { kind: 'game', id: shown.id }

  const choose = (key: PickKey) => {
    const ball = key.startsWith('g:') ? Number(key.slice(2)) : key.slice(2)
    setStadiumBalls((picking ?? []).map((v) => ({ id: v.id, original: v.ball })), ball)
  }

  const groups: PickerGroup<PickKey>[] = (() => {
    const mine = balls.filter((b) => b.original_id == null && !b.hidden && b.mesh && b.texture)
    const edited = new Map(balls.filter((b) => b.original_id != null).map((b) => [b.original_id!, b]))
    return [
      {
        label: t('stadium.groupProject'),
        items: mine
          .filter((b) => matches(query, b.name, b.credits))
          .map((b) => ({ key: `p:${b.uid}`, icon: <BallThumb ball={b} />, title: ballName(b, t('common.unnamed')), subtitle: <CreditsLink credits={b.credits} url={b.credits_url} /> })),
      },
      {
        label: t('stadium.groupGame'),
        items: gameBalls
          .filter((b) => matches(query, edited.get(b.id)?.name ?? gameName(b.id), String(b.id)))
          .map((b) => {
            const e = edited.get(b.id)
            return {
              key: `g:${b.id}`,
              icon: <BallThumb id={b.id} ball={e} />,
              title: e?.name.trim() ? ballName(e, '') : gameName(b.id),
              subtitle: t('stadium.ballId', { id: b.id }),
            }
          }),
      },
    ]
  })()

  const others = stadium.in_menu ? filters.filter((f) => stadium.filters.includes(f.id) && !GAME_MODES.some((m) => m.filter === f.id)) : []
  const versions = [...stadium.versions].sort((a, b) => Number(b.menu) - Number(a.menu)) // the one played first

  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{stadium.name}</h1>
          <span className="text-sm text-muted-foreground tabular-nums">
            {many ? t('stadium.ids', { first: stadium.versions[0].id, last: stadium.versions.at(-1)!.id }) : `#${stadium.id}`}
          </span>
          {stadium.lockable_id != null && (
            <Badge variant={locked ? 'outline' : 'secondary'} className="font-normal">
              {locked ? t('stadiums.locked') : t('stadiums.unlocked')}
            </Badge>
          )}
        </div>
        {stadium.lockable_id != null && (
          <Button variant="outline" size="sm" onClick={() => setStadiumLocked(stadium, !locked)}>
            {locked ? <LockOpen /> : <Lock />} {locked ? t('list.unlock') : t('list.lock')}
          </Button>
        )}
      </div>

      <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
        <div className="min-w-0 space-y-4 xl:flex-1">
          <Card>
            <CardHeader>
              <CardTitle>{t('stadium.ballTitle')}</CardTitle>
              <CardDescription>{many ? t('stadium.ballDescriptionVersions') : t('stadium.ballDescription')}</CardDescription>
              {many && (
                <CardAction>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setQuery('')
                      setPicking(stadium.versions)
                    }}
                  >
                    <Copy /> {t('stadium.applyAll')}
                  </Button>
                </CardAction>
              )}
            </CardHeader>
            <CardContent className="grid gap-2">
              {versions.map((v) => {
                const s = shownOf(v)
                const own = s.kind === 'project' ? s.ball : s.edited
                const changed = v.id in picked
                const hidden = hiddenPick(v)
                const link = s.kind === 'project' ? ballPath(ballKey(s.ball)) : ballPath(s.id)
                return (
                  <div
                    key={v.id}
                    className={cn('cursor-pointer rounded-lg border p-3', v.id === current.id && 'border-primary/60 bg-accent/40')}
                    onClick={() => setSelected(v.id)}
                  >
                    <div className="flex items-center gap-3">
                      <BallThumb ball={own} id={s.kind === 'game' ? s.id : undefined} className="size-12 rounded-full" />
                      <div className="min-w-0 flex-1">
                        {many && (
                          <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                            <span className="font-medium text-foreground">{REGION_LABELS[v.region] ? t(REGION_LABELS[v.region]) : v.id}</span>
                            <span className="tabular-nums">#{v.id}</span>
                            {v.menu ? (
                              <Badge variant="secondary" className="font-normal">
                                {t('stadium.regionMatches')}
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="font-normal" title={t('stadium.regionWorldTourHint')}>
                                {t('stadium.regionWorldTour')}
                              </Badge>
                            )}
                          </p>
                        )}
                        <p className="truncate font-medium">
                          <Link className="underline-offset-2 hover:underline" to={link} state={from.state} onClick={(e) => e.stopPropagation()}>
                            {nameOf(s)}
                          </Link>
                          {!changed && (
                            <Badge variant="outline" className="ml-2 font-normal">
                              {t('common.default')}
                            </Badge>
                          )}
                        </p>
                        {changed && <p className="truncate text-xs text-muted-foreground">{t('stadium.gameBall', { name: gameName(v.ball) })}</p>}
                      </div>
                      <div className="flex shrink-0 flex-col gap-1" onClick={(e) => e.stopPropagation()}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setQuery('')
                            setPicking([v])
                          }}
                        >
                          {t('playerBoots.change')}
                        </Button>
                        {changed && (
                          <Button variant="ghost" size="sm" onClick={() => setStadiumBalls([{ id: v.id, original: v.ball }], null)}>
                            <Repeat /> {t('playerBoots.useDefault')}
                          </Button>
                        )}
                      </div>
                    </div>
                    {hidden && (
                      <p className="mt-2 flex items-start gap-1 text-xs text-amber-600 dark:text-amber-500">
                        <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                        <span>{t('stadium.ballHidden', { ball: ballName(hidden, t('common.unnamed')) })}</span>
                      </p>
                    )}
                  </div>
                )
              })}
              <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <Info className="mt-0.5 size-3.5 shrink-0" />
                <span>{!stadium.in_menu ? t('stadium.notInMenusNote') : many ? t('stadium.versionsNote') : t('stadium.timesNote')}</span>
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('stadium.modesTitle')}</CardTitle>
              <CardDescription>{t('stadium.modesDescription')}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="flex flex-wrap gap-1.5">
                {modesOf(stadium).map((m) => (
                  <Badge key={m.filter} variant="secondary" className="font-normal">
                    {t(m.label)}
                  </Badge>
                ))}
                {!stadium.in_menu && (
                  <span className="text-sm text-muted-foreground">{stadium.free_roam ? t('stadium.freeRoam') : t('stadiums.notInMenus')}</span>
                )}
                {stadium.in_menu && !modesOf(stadium).length && (
                  <span className="text-sm text-muted-foreground">{t('stadiums.customOnly')}</span>
                )}
              </div>
              {others.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">{t('stadium.otherSetups')}</p>
                  <p className="text-sm">{others.map((f) => filterLabel(f, t)).join(' · ')}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('stadium.infoTitle')}</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <Info2 label={t('stadium.times')}>{[...new Set(stadium.times.map((x) => t(TIME_LABELS[x] ?? 'stadium.timeOther')))].join(', ')}</Info2>
              <Info2 label={t('stadium.surface')}>{SURFACE_LABELS[stadium.surface] ? t(SURFACE_LABELS[stadium.surface]) : stadium.surface}</Info2>
              <Info2 label={t('stadium.pitchSize')}>{t('stadium.pitchSizeValue', { size: stadium.pitch_size })}</Info2>
              <Info2 label={t('stadium.goal')}>{goalLabel(stadium.goal_type, t)}</Info2>
              <Info2 label={t('stadium.walls')}>{stadium.walls ? t('stadium.yes') : t('stadium.no')}</Info2>
              <Info2 label={t('stadium.capacity')}>{stadium.capacity.toLocaleString()}</Info2>
              <Info2 label={t('stadium.lock')}>
                {stadium.lockable_id != null ? (locked ? t('stadiums.locked') : t('stadiums.unlocked')) : t('stadiums.alwaysUnlocked')}
              </Info2>
              <Info2 label={t('stadium.versionsLabel')}>{many ? t('stadiums.versions', { count: stadium.versions.length }) : t('stadium.single')}</Info2>
            </CardContent>
          </Card>
        </div>

        {/* side by side (xl): as tall as the cards on the left, the 3D view taking all of it */}
        <Card className="order-first h-fit min-w-0 flex-1 gap-2 overflow-hidden py-0 xl:order-none xl:h-auto xl:self-stretch">
          <div className="aspect-[4/3] max-h-[60vh] w-full bg-gradient-to-b from-muted to-background xl:aspect-auto xl:max-h-none xl:min-h-80 xl:flex-1">
            <Suspense
              fallback={
                <div className="flex size-full items-center justify-center text-muted-foreground">
                  <LoaderCircle className="size-6 animate-spin" />
                </div>
              }
            >
              <BallPreview source={source} />
            </Suspense>
          </div>
          <p className="cursor-help px-4 pb-3 text-center text-xs text-muted-foreground" title={t('preview.controls')}>
            {many && REGION_LABELS[current.region]
              ? t('stadium.previewVersion', { version: t(REGION_LABELS[current.region]), name: nameOf(shown) })
              : t('stadium.preview', { name: nameOf(shown) })}
          </p>
        </Card>
      </div>

      <PickerDialog<PickKey>
        open={picking !== null}
        onOpenChange={(open) => !open && setPicking(null)}
        title={picking && picking.length > 1 ? t('stadium.pickAllTitle') : t('stadium.pickTitle')}
        description={t('stadium.pickDescription')}
        placeholder={t('balls.search')}
        query={query}
        onQuery={setQuery}
        groups={groups}
        empty={t('balls.noneFiltered')}
        actionLabel={t('playerBoots.pick')}
        onPick={(key) => {
          choose(key)
          setPicking(null)
        }}
      />
    </div>
  )
}
