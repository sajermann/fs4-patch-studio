import { LoaderCircle, Plus, RotateCcw, Shirt, Trash2 } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import type { KitKind, StreetPart, StreetPartName, Team } from '@/api/types'
import { ColorInput, Field, Stepper } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import type { MessageKey } from '@/i18n'
import { KIT_LABELS } from '@/lib/labels'
import { previewAppearance, STREET_PARTS, STREET_SLOTS, streetOutfit, streetPart } from '@/lib/preview'
import { rosterOf, teamKey } from '@/lib/players'
import { cn } from '@/lib/utils'
import { usePlayerDefaults, useProject } from '@/state/project'
import { useCatalog } from '@/state/queries'

const PlayerPreview = lazy(() => import('@/components/common/PlayerPreview'))

const PART_LABELS: Record<StreetPartName, MessageKey> = { top: 'street.top', bottom: 'street.bottom', socks: 'kit.socks' }
const COLOR_LABELS: MessageKey[] = ['street.colorPrimary', 'street.colorSecondary', 'street.colorTertiary']

/** Position in a list, counted from 1 like the steppers show it (the game's ids have gaps: 0, 1, 10, 20...). */
const listPosition = (list: number[], value: number) => list.indexOf(value) + 1 || value

/** Street Home/Away editor (the game's "Team Apparel"): the list of pieces of each part (model + variation), which the
 * game picks from for each player in each match, and the part's 3 mask colors, with the 3D player wearing the piece
 * selected in each list. Unset parts keep the template's pieces. */
export function StreetKitEditor({ team }: { team: Team }) {
  const { t } = useI18n()
  const { draft, updateTeam } = useProject()
  const catalog = useCatalog().data
  const [kind, setKind] = useState<KitKind>('home')
  const roster = rosterOf(draft, teamKey(team))
  const model = roster.find((p) => p.uid === team.captain) ?? roster[0]
  const defaults = usePlayerDefaults(model?.uid)
  const options = catalog?.street_options
  const [selected, setSelected] = useState<Partial<Record<StreetPartName, number>>>({})
  const selectedIn = (part: StreetPartName) => Math.min(selected[part] ?? 0, streetPart(team, kind, part, catalog).pieces.length - 1)
  const select = (part: StreetPartName, index: number) => setSelected((s) => ({ ...s, [part]: index }))

  const setPart = (part: StreetPartName, value: StreetPart | undefined) => {
    const kit = { ...team.street_kits?.[kind] }
    if (value) kit[part] = value
    else delete kit[part]
    const street_kits = { ...team.street_kits, [kind]: kit }
    if (!Object.keys(kit).length) delete street_kits[kind]
    updateTeam(team.uid, { street_kits })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shirt className="size-4" /> {t('street.title')}
        </CardTitle>
        <CardDescription>
          {t('street.description')} {t('street.goalkeeperNote')}
        </CardDescription>
        <CardAction>
          <div className="flex rounded-md border p-0.5 text-sm">
            {(['home', 'away'] as KitKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={cn('rounded px-3 py-1', kind === k ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              >
                {t(KIT_LABELS[k])}
              </button>
            ))}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="w-fit max-w-full space-y-5 lg:shrink-0">
          {STREET_PARTS.map((part) => {
            const own = team.street_kits?.[kind]?.[part]
            const { pieces } = streetPart(team, kind, part, catalog)
            const index = selectedIn(part)
            const piece = pieces[index]
            const styles = Object.keys(options?.[part] ?? {}).map(Number)
            const patterns = options?.[part]?.[piece.style] ?? []
            const setSlot = (slot: StreetPart['pieces'][number]) =>
              own && setPart(part, { ...own, pieces: own.pieces.map((p, i) => (i === index ? slot : p)) })
            return (
              <Field key={part} label={t(PART_LABELS[part])} entity={team.uid} field={`street_kits.${kind}.${part}`}>
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-1">
                    {pieces.map((p, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => select(part, i)}
                        title={t('street.pieceHint')}
                        className={cn('rounded-md border px-2 py-1 text-xs tabular-nums', i === index ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
                      >
                        {p.style < 0 ? t('street.noSocks') : `${listPosition(styles, p.style)} · ${listPosition(options?.[part]?.[p.style] ?? [], p.pattern)}`}
                      </button>
                    ))}
                    {own && own.pieces.length < STREET_SLOTS[part] && (
                      <Button
                        variant="ghost"
                        size="icon"
                        title={t('street.addPiece')}
                        aria-label={t('street.addPiece')}
                        onClick={() => {
                          setPart(part, { ...own, pieces: [...own.pieces, piece] })
                          select(part, own.pieces.length)
                        }}
                      >
                        <Plus />
                      </Button>
                    )}
                    {own && own.pieces.length > 1 && (
                      <Button
                        variant="ghost"
                        size="icon"
                        title={t('street.removePiece')}
                        aria-label={t('street.removePiece')}
                        onClick={() => setPart(part, { ...own, pieces: own.pieces.filter((_, i) => i !== index) })}
                      >
                        <Trash2 />
                      </Button>
                    )}
                  </div>
                  {own ? (
                    <>
                      <div className="flex flex-wrap items-end gap-3">
                        <div className="space-y-1">
                          <span className="text-xs text-muted-foreground">{t('street.style')}</span>
                          <Stepper
                            value={piece.style}
                            options={styles}
                            onChange={(style) => {
                              if (style === undefined) return
                              const list = options?.[part]?.[style] ?? []
                              setSlot({ style, pattern: list.includes(piece.pattern) ? piece.pattern : (list[0] ?? 0) })
                            }}
                          />
                        </div>
                        <div className="space-y-1">
                          <span className="text-xs text-muted-foreground">{t('street.pattern')}</span>
                          <Stepper value={piece.pattern} options={patterns} onChange={(pattern) => pattern !== undefined && setSlot({ ...piece, pattern })} />
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => setPart(part, undefined)} title={t('street.resetHint')}>
                          <RotateCcw /> {t('street.reset')}
                        </Button>
                      </div>
                      <div className="grid gap-2 sm:grid-cols-3">
                        {own.colors.map((c, i) => (
                          <div key={i} className="space-y-1">
                            <span className="text-xs text-muted-foreground">{t(COLOR_LABELS[i])}</span>
                            <ColorInput
                              value={c}
                              onChange={(v) => {
                                const colors = [...own.colors] as StreetPart['colors']
                                colors[i] = v
                                setPart(part, { ...own, colors })
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted-foreground">{t('street.random')}</span>
                      <Button variant="outline" size="sm" onClick={() => setPart(part, streetPart(team, kind, part, catalog))}>
                        {t('street.customize')}
                      </Button>
                    </div>
                  )}
                </div>
              </Field>
            )
          })}
        </div>
        <div className="aspect-[3/4] max-h-[75vh] w-full min-w-0 flex-1 overflow-hidden rounded-lg bg-gradient-to-b from-muted to-background">
          <Suspense
            fallback={
              <div className="flex size-full items-center justify-center text-muted-foreground">
                <LoaderCircle className="size-6 animate-spin" />
              </div>
            }
          >
            {catalog && <PlayerPreview appearance={previewAppearance(model, defaults, catalog)} outfit={streetOutfit(team, kind, catalog, { top: selectedIn('top'), bottom: selectedIn('bottom'), socks: selectedIn('socks') })} initialView="body" />}
          </Suspense>
        </div>
      </CardContent>
    </Card>
  )
}
