import { BadgeCheck, LoaderCircle, RotateCcw, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { ApiError, api, uiFontPreviewUrl } from '@/api/client'
import type { GamePatches, UiFont, UiFontSlot } from '@/api/types'
import { FieldIssues } from '@/components/common/form'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import { useProject } from '@/state/project'

type SwitchPatch = Exclude<keyof GamePatches, 'ui_fonts'>

/** Every on/off game patch the app knows, in the order shown (keys of GamePatches). */
const GAME_PATCHES: { id: SwitchPatch; title: MessageKey; description: MessageKey; note: MessageKey }[] = [
  {
    id: 'close_up_heads',
    title: 'patches.closeUpHeads.title',
    description: 'patches.closeUpHeads.description',
    note: 'patches.closeUpHeads.note',
  },
]

/** The menu fonts the user can replace, in the game's order (fsmod.uifonts.SLOTS). */
const UI_FONT_SLOTS: UiFontSlot[] = ['cn_bold', 'cn_regular', 'header', 'body', 'handwritten', 'courier', 'ea05_body']

/** Optional changes to the game itself (Project.game_patches), switched on per project; all off by default. */
export function PatchesPage() {
  const { t } = useI18n()
  const { draft, setDraft } = useProject()
  const enabled = (id: SwitchPatch) => !!draft.game_patches?.[id]
  const toggle = (id: SwitchPatch, on: boolean) =>
    setDraft((p) => ({ ...p, game_patches: { ...p.game_patches, [id]: on } }))

  return (
    <div className="space-y-6">
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
      <UiFontsCard />
    </div>
  )
}

/** Menu fonts (Project.game_patches.ui_fonts): a .ttf of the user's per font, or the game's. */
function UiFontsCard() {
  const { t } = useI18n()
  const { draft, setDraft } = useProject()
  const fonts = draft.game_patches?.ui_fonts ?? {}
  const setFont = (slot: UiFontSlot, font: UiFont | null) =>
    setDraft((p) => {
      const next = { ...p.game_patches?.ui_fonts }
      if (font) next[slot] = font
      else delete next[slot]
      return { ...p, game_patches: { ...p.game_patches, ui_fonts: next } }
    })

  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <CardTitle className="flex flex-wrap items-center gap-2">
          {t('patches.uiFonts.title')}
          <Badge variant="secondary" className="gap-1 font-normal">
            <BadgeCheck className="size-3.5" /> {t('patches.validated')}
          </Badge>
        </CardTitle>
        <CardDescription>{t('patches.uiFonts.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="divide-y rounded-md border">
          {UI_FONT_SLOTS.map((slot) => (
            <UiFontRow key={slot} slot={slot} font={fonts[slot]} onChange={(f) => setFont(slot, f)} />
          ))}
        </ul>
        <p className="text-xs text-muted-foreground">{t('patches.uiFonts.note')}</p>
      </CardContent>
    </Card>
  )
}

function UiFontRow({ slot, font, onChange }: { slot: UiFontSlot; font?: UiFont; onChange: (f: UiFont | null) => void }) {
  const { t } = useI18n()
  const { issues } = useProject()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [brokenPreview, setBrokenPreview] = useState<string | null | undefined>(undefined) // file whose preview failed
  const file = font?.file || null
  const field = `game_patches.ui_fonts.${slot}`

  const upload = async (picked: File) => {
    setBusy(true)
    try {
      const sent = await api.uploadUiFont(picked)
      onChange({ file: sent.path, name: sent.name })
      if (sent.missing_chars)
        toast.warning(t('patches.uiFonts.missingChars', { name: sent.name ?? picked.name, chars: sent.missing_chars }))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('patches.uiFonts.uploadFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="flex flex-col gap-3 p-3 md:flex-row md:items-center">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-medium">{t(`patches.uiFonts.slot.${slot}.title` as MessageKey)}</p>
        <p className="text-xs text-muted-foreground">{t(`patches.uiFonts.slot.${slot}.description` as MessageKey)}</p>
        <p className={file ? 'text-sm' : 'text-sm text-muted-foreground'}>
          {file ? (font?.name ?? file) : t('patches.uiFonts.game')}
        </p>
        <FieldIssues issues={issues.filter((i) => i.field === field)} />
      </div>
      <div className="flex shrink-0 flex-col items-start gap-2 md:items-end">
        {brokenPreview !== file && (
          <img
            src={uiFontPreviewUrl(slot, file)}
            alt={t('patches.uiFonts.previewAlt')}
            onError={() => setBrokenPreview(file)}
            className="h-9 max-w-full rounded bg-white px-1 object-contain object-left md:max-w-80"
          />
        )}
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            type="file"
            accept=".ttf"
            className="hidden"
            onChange={(e) => {
              const picked = e.target.files?.[0]
              e.target.value = ''
              if (picked) void upload(picked)
            }}
          />
          <Button variant="outline" size="sm" disabled={busy} onClick={() => input.current?.click()}>
            {busy ? <LoaderCircle className="animate-spin" /> : <Upload />}{' '}
            {file ? t('patches.uiFonts.replace') : t('patches.uiFonts.send')}
          </Button>
          {file && (
            <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
              <RotateCcw /> {t('patches.uiFonts.useGame')}
            </Button>
          )}
        </div>
      </div>
    </li>
  )
}
