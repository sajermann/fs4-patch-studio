import { AlertTriangle, Eye, Info, LoaderCircle, Repeat } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Glove, Player } from '@/api/types'
import type { GloveSource } from '@/components/common/GlovePreview'
import { GloveThumb } from '@/components/common/GloveThumb'
import { FieldIssues } from '@/components/common/form'
import { matches } from '@/components/common/list'
import { PickerDialog, type PickerGroup } from '@/components/common/PickerDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { gloveKey, gloveName, glovePath } from '@/lib/gloves'
import { playerName } from '@/lib/players'
import { useIssues, usePlayerDefaults, useProject } from '@/state/project'
import { useOriginalGloves } from '@/state/queries'

const GlovePreview = lazy(() => import('@/components/common/GlovePreview'))

/** What a player wears: a glove of the project, one of the game's gloves picked by code, or (nothing picked) the game
 * glove of his own or his template player's code. */
type Worn =
  | { kind: 'project'; glove: Glove }
  | { kind: 'game'; code: number; picked: boolean; edited?: Glove }
  | { kind: 'none' }

const DEFAULT_GLOVE = 1 // what the game shows for a code without files (fsmod.preview GLOVE_FALLBACK)

type PickKey = string // 'p:<uid>' (project glove) | 'g:<code>' (game glove)

/** The goalkeeper glove of a player (Accessories tab): picking one makes him a goalkeeper (his preferred position),
 * because the game only shows a goalkeeper's own glove. */
export function PlayerGloves({ player }: { player: Player }) {
  const { t } = useI18n()
  const { draft, updatePlayer } = useProject()
  const defaults = usePlayerDefaults(player.uid)
  const gameGloves = useOriginalGloves().data ?? []
  const gloves = draft.gloves ?? []
  const from = useFrom(playerName(player, t('common.unnamed'))) // the glove page's "←" comes back to this player
  const issues = useIssues(player.uid, 'glove')
  const [picking, setPicking] = useState(false)
  const [query, setQuery] = useState('')

  const worn: Worn = (() => {
    const g = player.glove
    if (typeof g === 'string') {
      const own = gloves.find((x) => x.uid === g && x.original_id == null)
      if (own && !own.hidden) return { kind: 'project', glove: own }
    }
    const picked = typeof g === 'number'
    const own = picked ? g : (player.appearance.gkglovetypecode ?? defaults?.appearance.gkglovetypecode)
    if (own === undefined) return { kind: 'none' }
    // a code without a glove of its own (0, most players) shows the game's glove 1 (seen in game)
    const code = gameGloves.length && !gameGloves.some((x) => x.code === own) ? DEFAULT_GLOVE : own || DEFAULT_GLOVE
    return { kind: 'game', code, picked, edited: gloves.find((x) => x.original_id === code) }
  })()
  const hiddenPick = typeof player.glove === 'string' ? gloves.find((x) => x.uid === player.glove && x.hidden) : undefined

  const choose = (key: PickKey | null) =>
    updatePlayer(player.uid, { glove: key === null ? undefined : key.startsWith('g:') ? Number(key.slice(2)) : key.slice(2) })

  const groups: PickerGroup<PickKey>[] = (() => {
    const mine = gloves.filter((g) => g.original_id == null && !g.hidden)
    const edited = new Map(gloves.filter((g) => g.original_id != null).map((g) => [g.original_id!, g]))
    return [
      {
        label: t('playerGloves.groupProject'),
        items: mine
          .filter((g) => matches(query, g.name, g.credits))
          .map((g) => ({
            key: `p:${g.uid}`,
            icon: <GloveThumb glove={g} />,
            title: gloveName(g, t('common.unnamed')),
            subtitle: g.credits,
          })),
      },
      {
        label: t('playerGloves.groupGame'),
        items: gameGloves
          .filter((g) => matches(query, edited.get(g.code)?.name ?? `Original ${g.code}`, String(g.code)))
          .map((g) => {
            const e = edited.get(g.code)
            return {
              key: `g:${g.code}`,
              icon: <GloveThumb code={g.code} glove={e} />,
              title: e ? gloveName(e, `Original ${g.code}`) : `Original ${g.code}`,
              subtitle: t('playerGloves.code', { code: g.code }),
            }
          }),
      },
    ]
  })()

  const source: GloveSource | null =
    worn.kind === 'project' && worn.glove.texture
      ? { kind: 'project', texture: worn.glove.texture }
      : worn.kind === 'game'
        ? worn.edited?.texture
          ? { kind: 'project', texture: worn.edited.texture }
          : { kind: 'game', code: worn.code }
        : null
  const glove = worn.kind === 'project' ? worn.glove : worn.kind === 'game' ? worn.edited : undefined
  const name =
    worn.kind === 'project'
      ? gloveName(worn.glove, t('common.unnamed'))
      : worn.kind === 'game'
        ? (worn.edited && gloveName(worn.edited, `Original ${worn.code}`)) || `Original ${worn.code}`
        : t('playerBoots.none')
  const credits = worn.kind === 'project' ? worn.glove.credits : worn.kind === 'game' ? (worn.edited?.credits ?? 'EA') : undefined
  const link = worn.kind === 'project' ? glovePath(gloveKey(worn.glove)) : worn.kind === 'game' ? glovePath(worn.code) : undefined
  const picked = player.glove != null

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <Card className="xl:w-[34rem] xl:shrink-0">
        <CardHeader>
          <CardTitle>{t('playerGloves.title')}</CardTitle>
          <CardDescription>{t('playerGloves.description')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="rounded-lg border p-3">
            <div className="flex items-center gap-3">
              <GloveThumb glove={glove} code={worn.kind === 'game' ? worn.code : undefined} className="size-14" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {link ? (
                    <Link className="underline-offset-2 hover:underline" to={link} state={from.state}>
                      {name}
                    </Link>
                  ) : (
                    name
                  )}
                  {!picked && (
                    <Badge variant="outline" className="ml-2 font-normal">
                      {t('common.default')}
                    </Badge>
                  )}
                </p>
                {credits && <p className="truncate text-xs text-muted-foreground">{t('playerBoots.credits', { credits })}</p>}
              </div>
              {/* as wide as the boots' Change button, whose column also holds "Show in preview" */}
              <div className="flex shrink-0 flex-col">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setQuery('')
                    setPicking(true)
                  }}
                >
                  {t('playerBoots.change')}
                </Button>
                <Button variant="ghost" size="sm" aria-hidden tabIndex={-1} className="invisible h-0 py-0">
                  <Eye /> {t('playerBoots.show')}
                </Button>
              </div>
            </div>
            {hiddenPick && (
              <p className="mt-2 flex items-start gap-1 text-xs text-amber-600 dark:text-amber-500">
                <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                <span>{t('issue.glove_hidden', { glove: gloveName(hiddenPick, t('common.unnamed')) })}</span>
              </p>
            )}
            <FieldIssues issues={issues.filter((i) => !(hiddenPick && i.code === 'glove_hidden'))} />
          </div>
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            <span>{picked ? t('playerGloves.makesGoalkeeper') : t('playerGloves.onlyGoalkeepers')}</span>
          </p>
          {picked && (
            <Button variant="ghost" size="sm" className="w-fit" onClick={() => choose(null)}>
              <Repeat /> {t('playerBoots.useDefault')}
            </Button>
          )}
        </CardContent>
      </Card>
      <Card className="order-first h-fit min-w-0 flex-1 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-none">
        <div className="aspect-[4/3] max-h-[50vh] w-full bg-gradient-to-b from-muted to-background">
          <Suspense
            fallback={
              <div className="flex size-full items-center justify-center text-muted-foreground">
                <LoaderCircle className="size-6 animate-spin" />
              </div>
            }
          >
            <GlovePreview source={source} />
          </Suspense>
        </div>
        <p className="px-4 pb-3 text-center text-xs text-muted-foreground" title={t('preview.controls')}>
          {t('playerGloves.preview')}
        </p>
      </Card>
      <PickerDialog<PickKey>
        open={picking}
        onOpenChange={setPicking}
        title={t('playerGloves.pickTitle')}
        description={t('playerGloves.pickDescription')}
        placeholder={t('gloves.search')}
        query={query}
        onQuery={setQuery}
        groups={groups}
        empty={t('gloves.noneFiltered')}
        actionLabel={t('playerBoots.pick')}
        onPick={(key) => {
          choose(key)
          setPicking(false)
        }}
      />
    </div>
  )
}
