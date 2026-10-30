import { Eye, Loader2, LoaderCircle, Trash2, Upload, X } from 'lucide-react'
import { lazy, Suspense, useRef, useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api, imageUrl } from '@/api/client'
import type { RealKit, RealKitFile, RealKitSlot, Team } from '@/api/types'
import { ColorInput, Field, FieldIssues, NumberInput } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n, type MessageKey } from '@/i18n'
import { NUMBER_COLORS, REAL_KIT_LABELS } from '@/lib/labels'
import { GOALKEEPER_POSITION, backName, previewAppearance, teamPreviewKit } from '@/lib/preview'
import { linkOf, rosterOf, teamKey } from '@/lib/players'
import { cn } from '@/lib/utils'
import { useIssues, usePlayerDefaults, useProject } from '@/state/project'
import { useCatalog, useOriginalPlayers, useOriginalTeams } from '@/state/queries'

const PlayerPreview = lazy(() => import('@/components/common/PlayerPreview'))

const SLOTS: RealKitSlot[] = ['home', 'away', 'goalkeeper']

const EMPTY_KIT: RealKit = {
  name_color: [255, 255, 255],
  number_color: 1,
  shorts_number_color: 1,
  collar: 0,
  front_number: false,
}

const FILES: { part: RealKitFile; label: MessageKey; hint: MessageKey | string; aspect: string }[] = [
  { part: 'thumbnail', label: 'realKit.thumbnail', hint: 'realKit.optional', aspect: 'aspect-square' },
  { part: 'jersey', label: 'kit.jersey', hint: '2048×2048', aspect: 'aspect-square' },
  { part: 'shorts', label: 'kit.shorts', hint: '2048×1024', aspect: 'aspect-[2/1]' },
]

/** One image of a real kit: click or drop to upload, the uploaded image is shown in place. */
function KitFileBox({
  team,
  slot,
  part,
  label,
  hint,
  aspect,
  value,
  onChange,
}: {
  team: Team
  slot: RealKitSlot
  part: RealKitFile
  label: string
  hint: string
  aspect: string
  value?: string
  onChange: (path: string | undefined) => void
}) {
  const { t } = useI18n()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const issues = useIssues(team.uid, `real_kits.${slot}.${part}`)

  const upload = async (file: File) => {
    setUploading(true)
    try {
      onChange((await api.uploadImage(file)).path)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('image.uploadFailed'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label>{label}</Label>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </div>
      <div
        className={cn(
          'relative flex cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-dashed bg-muted/40',
          aspect,
        )}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const f = e.dataTransfer.files[0]
          if (f) void upload(f)
        }}
      >
        {uploading ? (
          <Loader2 className="animate-spin" />
        ) : value ? (
          <img src={imageUrl(value)} alt={label} className="size-full object-contain" />
        ) : (
          <span className="flex flex-col items-center gap-1 p-2 text-center text-xs text-muted-foreground">
            <Upload className="size-4" /> {t('realKit.clickOrDrop')}
          </span>
        )}
        {value && !uploading && (
          <Button
            variant="secondary"
            size="icon"
            className="absolute top-1 right-1 size-6"
            title={t('realKit.removeImage')}
            onClick={(e) => {
              e.stopPropagation()
              onChange(undefined)
            }}
          >
            <X className="size-3" />
          </Button>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void upload(f)
          e.target.value = ''
        }}
      />
      <FieldIssues issues={issues} />
    </div>
  )
}

function NumberColorSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { t } = useI18n()
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {NUMBER_COLORS.map((c) => (
          <SelectItem key={c.value} value={String(c.value)}>
            <span className="size-3.5 rounded-sm border" style={{ background: c.hex }} />
            {t(c.label)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function RealKitCard({ team, slot, previewing, onPreview }: { team: Team; slot: RealKitSlot; previewing: boolean; onPreview: () => void }) {
  const { t } = useI18n()
  const { updateTeam } = useProject()
  const stored = team.real_kits?.[slot]
  const kit = { ...EMPTY_KIT, ...stored }
  const slotIssues = useIssues(team.uid, `real_kits.${slot}`)
  const set = (patch: Partial<RealKit>) => updateTeam(team.uid, { real_kits: { ...team.real_kits, [slot]: { ...kit, ...patch } } })
  const clear = () => {
    const real_kits = { ...team.real_kits }
    delete real_kits[slot]
    updateTeam(team.uid, { real_kits })
  }
  const field = (name: string) => `real_kits.${slot}.${name}`

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('realKit.title', { slot: t(REAL_KIT_LABELS[slot]) })}</CardTitle>
        <CardDescription>
          {slot === 'goalkeeper'
            ? t('realKit.goalkeeperDescription')
            : t('realKit.description')}
        </CardDescription>
        <CardAction className="flex gap-1">
          <Button variant={previewing ? 'secondary' : 'ghost'} size="sm" onClick={onPreview} title={t('realKit.previewHint')}>
            <Eye /> {t('realKit.preview')}
          </Button>
          {stored && (
            <Button variant="ghost" size="sm" onClick={clear}>
              <Trash2 /> {t('realKit.clear')}
            </Button>
          )}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <FieldIssues issues={slotIssues} />
        <div className="grid grid-cols-[1fr_1fr_2fr] gap-3">
          {FILES.map((f) => (
            <KitFileBox
              key={f.part}
              team={team}
              slot={slot}
              part={f.part}
              label={t(f.label)}
              hint={f.hint === 'realKit.optional' ? t(f.hint) : f.hint}
              aspect={f.aspect}
              value={kit[f.part]}
              onChange={(path) => set({ [f.part]: path })}
            />
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('realKit.nameColor')} entity={team.uid} field={field('name_color')}>
            <ColorInput value={kit.name_color} onChange={(v) => set({ name_color: v })} />
          </Field>
          <Field label={t('realKit.collar')} entity={team.uid} field={field('collar')} hint={t('realKit.collarHint')}>
            <NumberInput value={kit.collar} min={0} max={14} onChange={(v) => set({ collar: v ?? 0 })} />
          </Field>
          <Field label={t('realKit.jerseyNumber')} entity={team.uid} field={field('number_color')}>
            <NumberColorSelect value={kit.number_color} onChange={(v) => set({ number_color: v })} />
          </Field>
          <Field label={t('realKit.shortsNumber')} entity={team.uid} field={field('shorts_number_color')}>
            <NumberColorSelect value={kit.shorts_number_color} onChange={(v) => set({ shorts_number_color: v })} />
          </Field>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <Checkbox className="mt-0.5" checked={kit.front_number} onCheckedChange={(c) => set({ front_number: c === true })} />
          <span>
            {t('realKit.frontNumber')}
            <span className="block text-xs text-muted-foreground">{t('realKit.frontNumberHint')}</span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <Checkbox
            className="mt-0.5"
            checked={kit.shorts_number ?? false}
            onCheckedChange={(c) => set({ shorts_number: c === true })}
          />
          <span>
            {t('realKit.shortsNumberOn')}
            <span className="block text-xs text-muted-foreground">{t('realKit.shortsNumberOnHint')}</span>
          </span>
        </label>
      </CardContent>
    </Card>
  )
}

/** 3D player wearing one slot's kit as the build writes it (a slot without jersey and shorts shows the generic kit).
 * The model is the captain (or the first player); the goalkeeper kit goes on the team's goalkeeper when there is one. */
function RealKitPreview({ team, slot }: { team: Team; slot: RealKitSlot }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const catalog = useCatalog().data
  const key = teamKey(team)
  const roster = rosterOf(draft, key)
  const captain = roster.find((p) => p.uid === team.captain) ?? roster[0]
  const model = (slot === 'goalkeeper' && roster.find((p) => linkOf(p, key)?.position === GOALKEEPER_POSITION)) || captain
  const defaults = usePlayerDefaults(model?.uid)
  // original team: its game players (the captain, or the goalkeeper for the goalkeeper kit)
  const squad = useOriginalPlayers({ team: team.original_id ?? undefined, limit: 100 }, team.original_id != null).data?.items ?? []
  const gameCaptain = useOriginalTeams().data?.find((o) => o.id === team.original_id)?.captain
  const gameModel =
    (slot === 'goalkeeper' && squad.find((p) => p.position === GOALKEEPER_POSITION)) ||
    squad.find((p) => p.id === (team.captain ?? gameCaptain)) ||
    squad[0]
  const wearer =
    team.original_id != null
      ? gameModel && { number: gameModel.number, name: backName(gameModel) }
      : model && {
          number: linkOf(model, key)?.number ?? (defaults?.team === key ? defaults.number : undefined),
          name: backName(model),
        }
  return (
    <Card className="gap-2 overflow-hidden pb-0">
      <CardHeader>
        <CardTitle>{t('realKit.previewTitle', { slot: t(REAL_KIT_LABELS[slot]) })}</CardTitle>
        <CardDescription>{t('realKit.previewDescription')}</CardDescription>
      </CardHeader>
      <div className="aspect-[3/4] max-h-[75vh] w-full min-w-0 flex-1 bg-gradient-to-b from-muted to-background">
        <Suspense
          fallback={
            <div className="flex size-full items-center justify-center text-muted-foreground">
              <LoaderCircle className="size-6 animate-spin" />
            </div>
          }
        >
          {catalog && (
            <PlayerPreview
              appearance={previewAppearance(model, defaults, catalog)}
              outfit={{ kind: 'team', kit: teamPreviewKit(team, slot, wearer || undefined) }}
              initialView="body"
            />
          )}
        </Suspense>
      </div>
    </Card>
  )
}

/** Real kits (FIFA 14–16 packs): Home, Away and Goalkeeper, each from its PNGs, plus the 3D preview of one of them
 * (Home when the screen opens). */
export function RealKitEditor({ team }: { team: Team }) {
  const [previewSlot, setPreviewSlot] = useState<RealKitSlot>('home')
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {SLOTS.map((slot) => (
        <RealKitCard key={slot} team={team} slot={slot} previewing={previewSlot === slot} onPreview={() => setPreviewSlot(slot)} />
      ))}
      <RealKitPreview team={team} slot={previewSlot} />
    </div>
  )
}
