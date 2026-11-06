import { AlertTriangle, Eye, LoaderCircle, Repeat } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { SHOE_SURFACES, SURFACE_FIELDS, type Boot, type Player, type ShoeSurface } from '@/api/types'
import type { BootSource } from '@/components/common/BootPreview'
import { BootThumb } from '@/components/common/BootThumb'
import { FieldIssues } from '@/components/common/form'
import { PickerDialog, type PickerGroup } from '@/components/common/PickerDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import { matches } from '@/components/common/list'
import { useFrom } from '@/lib/back'
import { bootKey, bootName, bootPath, streetCode, SURFACE_LABELS } from '@/lib/boots'
import { playerName } from '@/lib/players'
import { cn } from '@/lib/utils'
import { useIssues, usePlayerDefaults, useProject } from '@/state/project'
import { useOriginalBoots } from '@/state/queries'

const BootPreview = lazy(() => import('@/components/common/BootPreview'))

/** What a player wears on one surface: a pack boot of the project, or one of the game's boots by code (his own
 * appearance code, or the one he inherits from his template player). */
type Worn = { kind: 'project'; boot: Boot } | { kind: 'game'; code: number; inherited: boolean; edited?: Boot } | { kind: 'none' }

type PickKey = string // 'p:<uid>' (project boot) | 'g:<code>' (game boot) | 'default'

/** Boots of a player, one per pitch surface (street = shoetypecode, society = turf_shoe, futsal = indoor_shoe),
 * with one 3D preview of the surface being looked at, like the kits. */
export function PlayerBoots({ player }: { player: Player }) {
  const { t } = useI18n()
  const { draft, updatePlayer } = useProject()
  const defaults = usePlayerDefaults(player.uid)
  const gameBoots = useOriginalBoots().data ?? []
  const boots = draft.boots ?? []
  const [shown, setShown] = useState<ShoeSurface>('street')
  const [picking, setPicking] = useState<ShoeSurface | null>(null)
  const [query, setQuery] = useState('')

  const worn = (surface: ShoeSurface): Worn => {
    const uid = player.boots?.[surface]
    const own = uid ? boots.find((b) => b.uid === uid && b.original_id == null) : undefined
    if (own && !own.hidden) return { kind: 'project', boot: own }
    const field = SURFACE_FIELDS[surface]
    const mine = player.appearance[field]
    // a player that only sets the street boot wears it everywhere (the build does the same)
    const street = surface !== 'street' && mine === undefined ? player.appearance.shoetypecode : undefined
    const code = mine ?? street ?? defaults?.appearance[field]
    if (code === undefined) return { kind: 'none' }
    return { kind: 'game', code, inherited: mine === undefined && street === undefined, edited: boots.find((b) => b.original_id === code) }
  }
  const all = SHOE_SURFACES.map(worn)

  const choose = (surfaces: ShoeSurface[], key: PickKey) => {
    const appearance = { ...player.appearance }
    const own: Partial<Record<ShoeSurface, string>> = { ...(player.boots ?? {}) }
    for (const s of surfaces) {
      delete own[s]
      if (key === 'default') delete appearance[SURFACE_FIELDS[s]]
      else if (key.startsWith('g:')) appearance[SURFACE_FIELDS[s]] = Number(key.slice(2))
      else own[s] = key.slice(2)
    }
    updatePlayer(player.uid, { appearance, boots: own })
  }

  // every boot is listed; on the street picker the ones the street takes come first and the others are there but
  // disabled, with the reason
  const streetPicker = picking === 'street'
  const streetFirst = <T,>(list: T[], ok: (x: T) => boolean) =>
    streetPicker ? [...list.filter(ok), ...list.filter((x) => !ok(x))] : list
  const groups: PickerGroup<PickKey>[] = (() => {
    const mine = boots.filter((b) => b.original_id == null && !b.hidden)
    const edited = new Map(boots.filter((b) => b.original_id != null).map((b) => [b.original_id!, b]))
    const streetNote = (ok: boolean) => (ok ? t('playerBoots.streetOk') : streetPicker ? t('playerBoots.notStreetMark') : t('playerBoots.notStreet'))
    return [
      {
        label: t('playerBoots.groupProject'),
        items: streetFirst(
          mine.filter((b) => matches(query, b.name, b.credits)),
          (b) => !!b.street,
        ).map((b) => ({
            key: `p:${b.uid}`,
            icon: <BootThumb boot={b} />,
            title: bootName(b, t('common.unnamed')),
            subtitle: [b.credits, streetNote(!!b.street)].filter(Boolean).join(' · '),
            disabled: streetPicker && !b.street,
        })),
      },
      {
        label: t('playerBoots.groupGame'),
        items: streetFirst(
          gameBoots.filter((b) => matches(query, edited.get(b.code)?.name ?? `Original ${b.code}`, String(b.code))),
          (b) => b.street,
        ).map((b) => {
            const e = edited.get(b.code)
            return {
              key: `g:${b.code}`,
              icon: <BootThumb code={b.code} boot={e} />,
              title: e ? bootName(e, `Original ${b.code}`) : `Original ${b.code}`,
              subtitle: [t('playerBoots.code', { code: b.code }), streetNote(b.street)].join(' · '),
              disabled: streetPicker && !b.street,
            }
        }),
      },
    ]
  })()

  const pick = (key: PickKey) => {
    if (picking) choose([picking], key)
    setPicking(null)
  }

  const shownWorn = all[SHOE_SURFACES.indexOf(shown)]
  const source: BootSource | null =
    shownWorn.kind === 'project' && shownWorn.boot.mesh && shownWorn.boot.texture
      ? { kind: 'project', mesh: shownWorn.boot.mesh, texture: shownWorn.boot.texture }
      : shownWorn.kind === 'game'
        ? shownWorn.edited?.mesh && shownWorn.edited.texture
          ? { kind: 'project', mesh: shownWorn.edited.mesh, texture: shownWorn.edited.texture }
          : { kind: 'game', code: shownWorn.code }
        : null

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <Card className="xl:w-[34rem] xl:shrink-0">
        <CardHeader>
          <CardTitle>{t('playerBoots.title')}</CardTitle>
          <CardDescription>{t('playerBoots.description')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {SHOE_SURFACES.map((surface, k) => (
            <Slot
              key={surface}
              player={player}
              surface={surface}
              worn={all[k]}
              active={shown === surface}
              onShow={() => setShown(surface)}
              onChange={() => {
                setQuery('')
                setPicking(surface)
              }}
            />
          ))}
          <Button variant="ghost" size="sm" className="w-fit" onClick={() => choose(SHOE_SURFACES, 'default')}>
            <Repeat /> {t('playerBoots.useDefault')}
          </Button>
        </CardContent>
      </Card>
      <Card className="order-first h-fit min-w-0 flex-1 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-none">
        <div className="aspect-[4/3] max-h-[70vh] w-full bg-gradient-to-b from-muted to-background">
          <Suspense
            fallback={
              <div className="flex size-full items-center justify-center text-muted-foreground">
                <LoaderCircle className="size-6 animate-spin" />
              </div>
            }
          >
            <BootPreview source={source} />
          </Suspense>
        </div>
        <p className="px-4 pb-3 text-center text-xs text-muted-foreground" title={t('preview.controls')}>
          {t('playerBoots.previewOf', { surface: t(SURFACE_LABELS[shown]) })}
        </p>
      </Card>
      <PickerDialog<PickKey>
        open={picking !== null}
        onOpenChange={(open) => !open && setPicking(null)}
        title={picking ? t('playerBoots.pickFor', { surface: t(SURFACE_LABELS[picking]) }) : ''}
        description={streetPicker ? t('playerBoots.pickStreetDescription') : t('playerBoots.pickDescription')}
        placeholder={t('boots.search')}
        query={query}
        onQuery={setQuery}
        groups={groups}
        empty={t('boots.noneFiltered')}
        actionLabel={t('playerBoots.pick')}
        onPick={pick}
      />
    </div>
  )
}

/** The "out of the patch" warning of a slot, with the boot's name as a link to its page. */
function HiddenBootWarning({ boot, from }: { boot: Boot; from: unknown }) {
  const { t } = useI18n()
  const MARK = '\u0000'
  const [before, after = ''] = t('issue.boot_hidden', { boot: MARK }).split(MARK)
  return (
    <p className="mt-1 flex items-start gap-1 text-xs text-amber-600 dark:text-amber-500">
      <AlertTriangle className="mt-0.5 size-3 shrink-0" />
      <span>
        {before}
        <Link className="font-medium underline underline-offset-2" to={bootPath(bootKey(boot))} state={from}>
          {bootName(boot, t('common.unnamed'))}
        </Link>
        {after}
      </span>
    </p>
  )
}

function Slot({
  player,
  surface,
  worn,
  active,
  onShow,
  onChange,
}: {
  player: Player
  surface: ShoeSurface
  worn: Worn
  active: boolean
  onShow: () => void
  onChange: () => void
}) {
  const { t } = useI18n()
  const from = useFrom(playerName(player, t('common.unnamed'))) // the boot page's "←" comes back to this player
  const issues = useIssues(player.uid, `boots.${surface}`)
  const fieldIssues = useIssues(player.uid, `appearance.${SURFACE_FIELDS[surface]}`)
  // the pack boot picked here but out of the patch: its warning links to the boot
  const { draft } = useProject()
  const hiddenIssue = issues.find((i) => i.code === 'boot_hidden')
  const hidden = (draft.boots ?? []).find((b) => b.uid === player.boots?.[surface] && b.original_id == null)
  const boot = worn.kind === 'project' ? worn.boot : worn.kind === 'game' ? worn.edited : undefined
  const name =
    worn.kind === 'project'
      ? bootName(worn.boot, t('common.unnamed'))
      : worn.kind === 'game'
        ? (worn.edited && bootName(worn.edited, `Original ${worn.code}`)) || `Original ${worn.code}`
        : t('playerBoots.none')
  const credits = worn.kind === 'project' ? worn.boot.credits : worn.kind === 'game' ? (worn.edited?.credits ?? 'EA') : undefined
  const link = worn.kind === 'project' ? bootPath(bootKey(worn.boot)) : worn.kind === 'game' ? bootPath(worn.code) : undefined
  const offStreet = surface === 'street' && worn.kind === 'game' && !streetCode(worn.code)
  return (
    <div className={cn('rounded-lg border p-3', active && 'border-primary')}>
      <div className="flex items-center gap-3">
        <BootThumb boot={boot} code={worn.kind === 'game' ? worn.code : undefined} className="h-12 w-24" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-muted-foreground uppercase">{t(SURFACE_LABELS[surface])}</p>
          <p className="truncate font-medium">
            {link ? (
              <Link className="underline-offset-2 hover:underline" to={link} state={from.state}>
                {name}
              </Link>
            ) : (
              name
            )}
            {worn.kind === 'game' && worn.inherited && (
              <Badge variant="outline" className="ml-2 font-normal">
                {t('common.default')}
              </Badge>
            )}
          </p>
          {credits && <p className="truncate text-xs text-muted-foreground">{t('playerBoots.credits', { credits })}</p>}
        </div>
        <div className="flex shrink-0 flex-col gap-1">
          <Button variant="outline" size="sm" onClick={onChange}>
            {t('playerBoots.change')}
          </Button>
          <Button variant={active ? 'secondary' : 'ghost'} size="sm" onClick={onShow}>
            <Eye /> {t('playerBoots.show')}
          </Button>
        </div>
      </div>
      {offStreet && <p className="mt-2 text-xs text-amber-600 dark:text-amber-500">{t('playerBoots.offStreet')}</p>}
      {hiddenIssue && hidden && <HiddenBootWarning boot={hidden} from={from.state} />}
      <FieldIssues issues={[...issues.filter((i) => !(hidden && i === hiddenIssue)), ...fieldIssues]} />
    </div>
  )
}
