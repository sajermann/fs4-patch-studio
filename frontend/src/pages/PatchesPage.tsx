import { BadgeCheck } from 'lucide-react'
import type { GamePatches } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { useI18n, type MessageKey } from '@/i18n'
import { useProject } from '@/state/project'

/** Every game patch the app knows, in the order shown (keys of GamePatches). */
const GAME_PATCHES: { id: keyof GamePatches; title: MessageKey; description: MessageKey; note: MessageKey }[] = [
  {
    id: 'close_up_heads',
    title: 'patches.closeUpHeads.title',
    description: 'patches.closeUpHeads.description',
    note: 'patches.closeUpHeads.note',
  },
]

/** Optional changes to the game itself (Project.game_patches), switched on per project; all off by default. */
export function PatchesPage() {
  const { t } = useI18n()
  const { draft, setDraft } = useProject()
  const enabled = (id: keyof GamePatches) => !!draft.game_patches?.[id]
  const toggle = (id: keyof GamePatches, on: boolean) =>
    setDraft((p) => ({ ...p, game_patches: { ...p.game_patches, [id]: on } }))

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('nav.patches')}</h1>
        <p className="text-sm text-muted-foreground">{t('patches.description')}</p>
      </div>
      {GAME_PATCHES.map((p) => {
        const on = enabled(p.id)
        const switchId = `game-patch-${p.id}`
        return (
          <Card key={p.id}>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div className="space-y-1.5">
                <CardTitle className="flex flex-wrap items-center gap-2">
                  <label htmlFor={switchId} className="cursor-pointer">
                    {t(p.title)}
                  </label>
                  <Badge variant="secondary" className="gap-1 font-normal">
                    <BadgeCheck className="size-3.5" /> {t('patches.validated')}
                  </Badge>
                </CardTitle>
                <CardDescription>{t(p.description)}</CardDescription>
              </div>
              <div className="flex shrink-0 items-center gap-2 pt-0.5">
                <span className="text-sm text-muted-foreground">{t(on ? 'patches.enabled' : 'patches.disabled')}</span>
                <Switch id={switchId} checked={on} onCheckedChange={(v) => toggle(p.id, v)} />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">{t(p.note)}</p>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
