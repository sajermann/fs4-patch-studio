import { LoaderCircle, RotateCcw, Shirt } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import type { KitKind, StreetPartName, StreetPiece, Team } from '@/api/types'
import { ColorInput, Field, Stepper } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useI18n } from '@/i18n'
import type { MessageKey } from '@/i18n'
import { KIT_LABELS } from '@/lib/labels'
import { previewAppearance, STREET_PARTS, streetOutfit, streetPiece } from '@/lib/preview'
import { rosterOf, teamKey } from '@/lib/players'
import { cn } from '@/lib/utils'
import { usePlayerDefaults, useProject } from '@/state/project'
import { useCatalog } from '@/state/queries'

const PlayerPreview = lazy(() => import('@/components/common/PlayerPreview'))

const PART_LABELS: Record<StreetPartName, MessageKey> = { top: 'street.top', bottom: 'street.bottom', socks: 'kit.socks' }
const COLOR_LABELS: MessageKey[] = ['street.colorPrimary', 'street.colorSecondary', 'street.colorTertiary']

/** Street Home/Away editor (the game's "Team Apparel"): pick each piece (model + variation) and its 3 mask colors,
 * with the 3D player wearing it live. Unset parts keep the template's pieces (the game picks one at random). */
export function StreetKitEditor({ team }: { team: Team }) {
  const { t } = useI18n()
  const { draft, updateTeam } = useProject()
  const catalog = useCatalog().data
  const [kind, setKind] = useState<KitKind>('home')
  const roster = rosterOf(draft, teamKey(team))
  const model = roster.find((p) => p.uid === team.captain) ?? roster[0]
  const defaults = usePlayerDefaults(model?.uid)
  const options = catalog?.street_options

  const setPiece = (part: StreetPartName, piece: StreetPiece | undefined) => {
    const kit = { ...team.street_kits?.[kind] }
    if (piece) kit[part] = piece
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
          {t('street.description')}
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
            const piece = streetPiece(team, kind, part, catalog)
            const styles = Object.keys(options?.[part] ?? {}).map(Number)
            const patterns = options?.[part]?.[piece.style] ?? []
            const customize = () => setPiece(part, piece)
            return (
              <Field key={part} label={t(PART_LABELS[part])} entity={team.uid} field={`street_kits.${kind}.${part}`}>
                {own ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-end gap-3">
                      <div className="space-y-1">
                        <span className="text-xs text-muted-foreground">{t('street.style')}</span>
                        <Stepper
                          value={own.style}
                          options={styles}
                          onChange={(style) => {
                            if (style === undefined) return
                            const list = options?.[part]?.[style] ?? []
                            setPiece(part, { ...own, style, pattern: list.includes(own.pattern) ? own.pattern : (list[0] ?? 0) })
                          }}
                        />
                      </div>
                      <div className="space-y-1">
                        <span className="text-xs text-muted-foreground">{t('street.pattern')}</span>
                        <Stepper value={own.pattern} options={patterns} onChange={(pattern) => pattern !== undefined && setPiece(part, { ...own, pattern })} />
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => setPiece(part, undefined)} title={t('street.resetHint')}>
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
                              const colors = [...own.colors] as StreetPiece['colors']
                              colors[i] = v
                              setPiece(part, { ...own, colors })
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">{t('street.random')}</span>
                    <Button variant="outline" size="sm" onClick={customize}>
                      {t('street.customize')}
                    </Button>
                  </div>
                )}
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
            {catalog && <PlayerPreview appearance={previewAppearance(model, defaults, catalog)} outfit={streetOutfit(team, kind, catalog)} initialView="body" />}
          </Suspense>
        </div>
      </CardContent>
    </Card>
  )
}
