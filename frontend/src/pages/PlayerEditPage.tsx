import { AlertTriangle, Copy, DatabaseZap, Dices, Eraser, LoaderCircle, Trash2, User } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { photoPreviewUrl, scannedFaceQuery, type FaceSource } from '@/api/client'
import { HAIR_MODES, HAIR_THICKNESS, THICK_HAIR_MODES, type HairMode, type Player } from '@/api/types'
import { BaseDataDialog } from '@/components/common/BaseDataDialog'
import { FacePicker, type BrowsedFace } from '@/components/common/FacePicker'
import { EntityIssues, Field, NumberInput, Stepper } from '@/components/common/form'
import { PhotoCard, PlayerAvatar } from '@/components/common/PlayerPhoto'
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
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { BackButton, useBack, useGoBack, useKeepBack, useTabParam } from '@/lib/back'
import { useI18n, type MessageKey, type TFunction } from '@/i18n'
import { useCopy } from '@/lib/copy'
import { APPEARANCE_LABELS, FOOT_LABELS, SKILL_LABELS } from '@/lib/labels'
import { computeOverall } from '@/lib/skills'
import { GOALKEEPER_POSITION, backName, previewAppearance, teamPreviewKit } from '@/lib/preview'
import { cn } from '@/lib/utils'
import { usePlayerDefaults, useProject } from '@/state/project'
import { useCatalog, useLookups, useStatus } from '@/state/queries'

const PlayerPreview = lazy(() => import('@/components/common/PlayerPreview'))

const NONE = 'none'
// codes that still matter with a real face: the scalp hair color (painted by the converter), the body skin and the body
const FACE_MODE_CODES = ['haircolorcode', 'skintonecode', 'bodytypecode', 'shoetypecode', 'gkglovetypecode', 'jerseysleevelengthcode', 'socklengthcode']
const FACE_MODE_LABELS: Record<string, MessageKey> = { haircolorcode: 'playerEdit.faceHairColor', skintonecode: 'playerEdit.faceSkinTone' }
// The profile label in the player card is not stored anywhere: the game shows the label of the highest of these
// 7 bars. Confirmed in game: SHO -> Finisher, ATH -> Powerhouse.
const STYLE_BY_SKILL: Record<string, string> = {
  SHO: 'Finisher',
  SPE: 'Sprinter',
  DEF: 'Stopper',
  GK: 'Keeper',
  PAS: 'Playmaker',
  ATH: 'Powerhouse',
  DRI: 'Dribbler',
}

/** "<value> (default)" for values inherited from the template player. */
const inherited = (t: TFunction, value: string | number | null | undefined) =>
  value === null || value === undefined || value === '' ? t('common.default') : t('common.inherited', { value })

function DataTab({ player }: { player: Player }) {
  const { t } = useI18n()
  const { draft, updatePlayer } = useProject()
  const catalog = useCatalog().data
  const lookups = useLookups()
  const defaults = usePlayerDefaults(player.uid)
  const set = (patch: Partial<Player>) => updatePlayer(player.uid, patch)
  const [hMin, hMax] = catalog?.ranges.height ?? [150, 277]
  const [wMin, wMax] = catalog?.ranges.weight ?? [40, 167]
  const nationality = player.fields.nationality
  const positionAbbr = defaults?.position != null ? lookups.position.get(defaults.position) : undefined

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
      <Card>
        <CardContent className="grid gap-4 pt-6 sm:grid-cols-2">
          <Field label={t('playerEdit.firstName')} entity={player.uid} field="first_name">
            <Input value={player.first_name} onChange={(e) => set({ first_name: e.target.value })} autoFocus={!player.first_name} />
          </Field>
          <Field label={t('playerEdit.lastName')} entity={player.uid} field="last_name">
            <Input value={player.last_name} onChange={(e) => set({ last_name: e.target.value })} />
          </Field>
          <Field label={t('playerEdit.displayName')} entity={player.uid} field="display_name" hint={t('playerEdit.displayNameHint')}>
            <Input
              value={player.display_name ?? ''}
              placeholder={`${player.first_name} ${player.last_name}`.trim()}
              onChange={(e) => set({ display_name: e.target.value || undefined })}
            />
          </Field>
          <Field label={t('playerEdit.jerseyName')} entity={player.uid} field="jersey_name" hint={t('playerEdit.jerseyNameHint')}>
            <Input
              value={player.jersey_name ?? ''}
              placeholder={player.last_name}
              onChange={(e) => set({ jersey_name: e.target.value || undefined })}
            />
          </Field>
          <Field label={t('players.colTeam')} entity={player.uid} field="team">
            <Select value={player.team ?? NONE} onValueChange={(v) => set({ team: v === NONE ? null : v })}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t('playerEdit.noTeam')}</SelectItem>
                {draft.teams.filter((tm) => tm.original_id == null).map((tm) => (
                  <SelectItem key={tm.uid} value={tm.uid}>
                    {tm.name || t('team.unnamed')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t('teamEdit.number')} entity={player.uid} field="number">
              <NumberInput value={player.number} onChange={(v) => set({ number: v })} min={1} max={99} placeholder={inherited(t, defaults?.number)} />
            </Field>
            <Field label={t('players.colPosition')} entity={player.uid} field="position">
              <Select
                value={player.position === undefined ? NONE : String(player.position)}
                onValueChange={(v) => set({ position: v === NONE ? undefined : Number(v) })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>{inherited(t, positionAbbr)}</SelectItem>
                  {(catalog?.positions ?? []).map((p) => (
                    <SelectItem key={p.code} value={String(p.code)}>
                      {p.abbr}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label={t('playerEdit.height')} entity={player.uid} field="height">
              <NumberInput value={player.height} onChange={(v) => set({ height: v })} min={hMin} max={hMax} placeholder={inherited(t, defaults?.height)} />
            </Field>
            <Field label={t('playerEdit.weight')} entity={player.uid} field="weight">
              <NumberInput value={player.weight} onChange={(v) => set({ weight: v })} min={wMin} max={wMax} placeholder={inherited(t, defaults?.weight)} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field
              label={t('base.birthdate')}
              entity={player.uid}
              field="birthdate"
              hint={
                !player.birthdate && defaults?.birthdate
                  ? t('playerEdit.birthdateDefault', { date: defaults.birthdate.split('-').reverse().join('/') })
                  : undefined
              }
            >
              <Input type="date" value={player.birthdate ?? ''} onChange={(e) => set({ birthdate: e.target.value || undefined })} />
            </Field>
            <Field label={t('base.foot')} entity={player.uid} field="foot">
              <Select value={player.foot ?? NONE} onValueChange={(v) => set({ foot: v === NONE ? undefined : (v as Player['foot']) })}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>{inherited(t, defaults && t(FOOT_LABELS[defaults.foot]))}</SelectItem>
                  <SelectItem value="right">{t(FOOT_LABELS.right)}</SelectItem>
                  <SelectItem value="left">{t(FOOT_LABELS.left)}</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>
          <Field label={t('base.nationality')} entity={player.uid} field="fields.nationality">
            <Select
              value={nationality === undefined ? NONE : String(nationality)}
              onValueChange={(v) => {
                const fields = { ...player.fields }
                if (v === NONE) delete fields.nationality
                else fields.nationality = Number(v)
                set({ fields })
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{inherited(t, defaults && lookups.nation.get(defaults.nationality))}</SelectItem>
                {(catalog?.nations ?? []).map((n) => (
                  <SelectItem key={n.id} value={String(n.id)}>
                    {n.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <div className="flex items-center gap-2 sm:col-span-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="flex items-center gap-2">
                  <Checkbox id="generic" checked={player.generic} disabled />
                  <Label htmlFor="generic" className="font-normal">
                    {t('playerEdit.generic')}
                  </Label>
                </span>
              </TooltipTrigger>
              <TooltipContent>{t('playerEdit.genericHint')}</TooltipContent>
            </Tooltip>
          </div>
        </CardContent>
      </Card>
      <PhotoCard player={player} />
    </div>
  )
}

function SkillsTab({ player }: { player: Player }) {
  const { t } = useI18n()
  const { updatePlayer } = useProject()
  const catalog = useCatalog().data
  const defaults = usePlayerDefaults(player.uid)
  const skills = catalog?.skills ?? {}
  // every change also stores the recalculated overall
  const withOverall = (own: Record<string, number>) => {
    const bars = Object.fromEntries(Object.entries(own).filter(([k]) => k !== 'overall'))
    const overall = computeOverall((k) => bars[k] ?? defaults?.skills[k])
    return overall === undefined ? bars : { ...bars, overall }
  }
  const setSkill = (key: string, value: number) => updatePlayer(player.uid, { skills: withOverall({ ...player.skills, [key]: value }) })
  const effective = (key: string): number | undefined => player.skills[key] ?? defaults?.skills[key]
  const overall = computeOverall(effective)

  // the label is derived from the effective bars (own value, else the template player's)
  const barKeys = Object.keys(STYLE_BY_SKILL)
  const known = barKeys.every((k) => effective(k) !== undefined)
  const highest = known ? Math.max(...barKeys.map((k) => effective(k)!)) : undefined
  const leaders = known ? barKeys.filter((k) => effective(k) === highest) : []

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('base.skills')}</CardTitle>
        <CardDescription>{t('playerEdit.skillsDescription')}</CardDescription>
        <CardAction>
          <Button variant="ghost" size="sm" onClick={() => updatePlayer(player.uid, { skills: withOverall({}) })}>
            <Eraser /> {t('playerEdit.resetDefault')}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
        <div className="rounded-lg border bg-muted/40 p-3 sm:col-span-2">
          <p className="text-xs text-muted-foreground">{t('playerEdit.profile')}</p>
          {!known ? (
            <p className="text-sm text-muted-foreground">{t('playerEdit.calculating')}</p>
          ) : (
            <p className="text-lg font-semibold tracking-wide">
              {leaders.map((k) => STYLE_BY_SKILL[k].toUpperCase()).join(' / ')}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {leaders.length > 1
                  ? t('playerEdit.profileTie', { value: highest })
                  : t('playerEdit.profileHighest', { bar: leaders[0], value: highest })}
              </span>
            </p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {t('playerEdit.profileHint')}
          </p>
        </div>
        {Object.entries(skills).map(([key, { min, max }]) => {
          if (key === 'overall') {
            return (
              <Field
                key={key}
                label={SKILL_LABELS[key] ? t(SKILL_LABELS[key]) : key}
                entity={player.uid}
                field="skills.overall"
                hint={t('playerEdit.overallHint')}
              >
                <div className="flex items-center gap-3">
                  <Slider min={min} max={max} step={1} value={[overall ?? min]} disabled />
                  <span className="w-24 shrink-0 text-right text-sm tabular-nums">{overall ?? '…'}</span>
                </div>
              </Field>
            )
          }
          const own = player.skills[key]
          const value = effective(key)
          return (
            <Field key={key} label={SKILL_LABELS[key] ? t(SKILL_LABELS[key]) : key} entity={player.uid} field={`skills.${key}`}>
              <div className="flex items-center gap-3">
                <Slider
                  min={min}
                  max={max}
                  step={1}
                  value={[value ?? Math.round((min + max) / 2)]}
                  onValueChange={([v]) => setSkill(key, v)}
                  className={own === undefined ? 'opacity-50' : ''}
                />
                <span className="w-24 shrink-0 text-right text-sm tabular-nums">
                  {own !== undefined ? own : <span className="text-muted-foreground">{inherited(t, value)}</span>}
                </span>
              </div>
            </Field>
          )
        })}
      </CardContent>
    </Card>
  )
}

const HAIR_MODE_LABELS: Record<HairMode, MessageKey> = {
  standard: 'playerEdit.hairModeStandard',
  volume: 'playerEdit.hairModeVolume',
  split: 'playerEdit.hairModeSplit',
  split_sharp: 'playerEdit.hairModeSplitSharp',
  split_sharp_thick: 'playerEdit.hairModeSplitSharpThick',
}
const HAIR_MODE_HINTS: Record<HairMode, MessageKey> = {
  standard: 'playerEdit.hairModeStandardHint',
  volume: 'playerEdit.hairModeVolumeHint',
  split: 'playerEdit.hairModeSplitHint',
  split_sharp: 'playerEdit.hairModeSplitSharpHint',
  split_sharp_thick: 'playerEdit.hairModeSplitSharpThickHint',
}

/** Strand thickness of the thick hair converter; saved on release only (each value converts the face again). */
function HairThickness({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const { t } = useI18n()
  const [shown, setShown] = useState(value)
  useEffect(() => setShown(value), [value])
  return (
    <div className="mt-3 grid gap-1.5 text-sm">
      <Label>{t('playerEdit.hairThickness')}</Label>
      <div className="flex items-center gap-3">
        <Slider
          min={0}
          max={HAIR_THICKNESS.max}
          step={HAIR_THICKNESS.step}
          value={[shown]}
          onValueChange={([v]) => setShown(v)}
          onValueCommit={([v]) => onCommit(Math.round(v * 10) / 10)}
        />
        <span className="w-8 shrink-0 text-right tabular-nums">{shown.toFixed(1)}</span>
      </div>
      <span className="text-xs text-muted-foreground">{t('playerEdit.hairThicknessHint')}</span>
    </div>
  )
}

function AppearanceTab({ player }: { player: Player }) {
  const { t } = useI18n()
  const { draft, updatePlayer } = useProject()
  const catalog = useCatalog().data
  const options = catalog?.appearance ?? {}
  const defaults = usePlayerDefaults(player.uid)
  const preview = previewAppearance(player, defaults, catalog)
  const [browsing, setBrowsing] = useState<BrowsedFace | null>(null)
  const generic = player.generic
  // the converter paints the scalp with the player's hair color (fsmod.scanface)
  const hairColorCode = player.appearance.haircolorcode ?? defaults?.appearance.haircolorcode ?? options.haircolorcode?.[0] ?? 0
  const faceSource: FaceSource | null = browsing
    ? { folder: browsing.folder, face: browsing.face.id }
    : !generic && player.face
      ? { player: player.uid, face: player.face.source_id }
      : null
  const paintScalp = player.face?.paint_scalp ?? true
  const hairMode = player.face?.hair_mode ?? 'standard'
  const thickHair = THICK_HAIR_MODES.includes(hairMode)
  const hairThickness = player.face?.hair_thickness ?? HAIR_THICKNESS.default
  const scanned = faceSource
    ? { query: scannedFaceQuery(faceSource, hairColorCode, paintScalp, hairMode, thickHair ? hairThickness : undefined) }
    : null
  // Team Home kit of the player's team (the goalkeeper kit for a goalkeeper; neutral grey for free agents)
  const team = player.team ? draft.teams.find((tm) => tm.uid === player.team) : undefined
  const kit = teamPreviewKit(team, (player.position ?? defaults?.position) === GOALKEEPER_POSITION ? 'goalkeeper' : 'home', {
    number: player.number ?? defaults?.number,
    name: backName(player),
  })
  const set = (code: string, value: number | undefined) => {
    const appearance = { ...player.appearance }
    if (value === undefined) delete appearance[code]
    else appearance[code] = value
    updatePlayer(player.uid, { appearance })
  }
  const randomize = () => {
    const appearance: Record<string, number> = {}
    for (const code of ['headtypecode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'facialhairtypecode', 'eyecolorcode']) {
      const list = options[code] ?? []
      if (list.length) appearance[code] = list[Math.floor(Math.random() * list.length)]
    }
    updatePlayer(player.uid, { appearance: { ...player.appearance, ...appearance } })
  }

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <Card className="order-3 w-fit max-w-full xl:order-1 xl:max-w-[26rem] xl:shrink-0">
        <CardHeader>
          <CardTitle>{t('playerEdit.tabLook')}</CardTitle>
          <div className="flex w-fit rounded-md border p-0.5 text-sm">
            {([true, false] as const).map((g) => (
              <button
                key={String(g)}
                type="button"
                onClick={() => {
                  updatePlayer(player.uid, { generic: g })
                  if (g) setBrowsing(null)
                }}
                className={cn('rounded px-3 py-1', generic === g ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              >
                {g ? t('playerEdit.genericHead') : t('playerEdit.realFace')}
              </button>
            ))}
          </div>
          <CardDescription>
            {generic ? t('playerEdit.lookGenericDescription') : t('playerEdit.lookFaceDescription')}
          </CardDescription>
          <div className="flex gap-1 pt-1">
            {generic && (
              <Button variant="outline" size="sm" onClick={randomize}>
                <Dices /> {t('playerEdit.randomize')}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => updatePlayer(player.uid, { appearance: {} })}>
              <Eraser /> {t('playerEdit.resetDefault')}
            </Button>
          </div>
        </CardHeader>
        {!generic && (
          <CardContent>
            <FacePicker key={player.uid} player={player} browsing={browsing} onBrowse={setBrowsing} />
            {player.face && (
              <label className="mt-3 flex items-start gap-2 text-sm">
                <Checkbox
                  className="mt-0.5"
                  checked={paintScalp}
                  onCheckedChange={(v) => player.face && updatePlayer(player.uid, { face: { ...player.face, paint_scalp: v === true } })}
                />
                <span>
                  {t('playerEdit.paintScalp')}
                  <span className="block text-xs text-muted-foreground">{t('playerEdit.paintScalpHint')}</span>
                </span>
              </label>
            )}
            {player.face && (
              <div className="mt-3 grid gap-1.5 text-sm">
                <Label>{t('playerEdit.hairMode')}</Label>
                <Select
                  value={hairMode}
                  onValueChange={(v) => player.face && updatePlayer(player.uid, { face: { ...player.face, hair_mode: v as HairMode } })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {HAIR_MODES.map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {t(HAIR_MODE_LABELS[mode])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <span className="text-xs text-muted-foreground">{t(HAIR_MODE_HINTS[hairMode])}</span>
              </div>
            )}
            {player.face && thickHair && (
              <HairThickness
                value={hairThickness}
                onCommit={(v) => player.face && updatePlayer(player.uid, { face: { ...player.face, hair_thickness: v } })}
              />
            )}
          </CardContent>
        )}
        <CardContent className="grid gap-x-6 gap-y-4 sm:grid-cols-[repeat(2,11.5rem)]">
          {Object.keys(APPEARANCE_LABELS)
            .filter((code) => options[code] && (generic || FACE_MODE_CODES.includes(code)))
            .map((code) => (
              <Field key={code} label={t((!generic && FACE_MODE_LABELS[code]) || APPEARANCE_LABELS[code])} entity={player.uid} field={`appearance.${code}`}>
                <Stepper
                  value={player.appearance[code]}
                  options={options[code]}
                  onChange={(v) => set(code, v)}
                  inherited={defaults?.appearance[code]}
                />
                {code === 'bodytypecode' && (
                  <p className="mt-1 flex items-start gap-1 text-xs text-amber-600 dark:text-amber-500">
                    <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                    {t('playerEdit.bodyTypeWarning')}
                  </p>
                )}
              </Field>
            ))}
        </CardContent>
      </Card>
      {/* the 3D preview takes all the free width, pushing the reference photo to the right */}
      <Card className="order-1 h-fit min-w-0 flex-1 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-2">
        <div className="aspect-[3/4] max-h-[75vh] w-full bg-gradient-to-b from-muted to-background">
          <Suspense
            fallback={
              <div className="flex size-full items-center justify-center text-muted-foreground">
                <LoaderCircle className="size-6 animate-spin" />
              </div>
            }
          >
            {catalog && (
              <PlayerPreview
                appearance={preview}
                outfit={{ kind: 'team', kit }}
                face={scanned}
                closeUpOnly={!!draft.game_patches?.close_up_heads}
              />
            )}
          </Suspense>
        </div>
        <p
          className="cursor-help px-4 pb-3 text-center text-xs text-muted-foreground"
          title={t('preview.controls')}
        >
          {t('preview.label')}
        </p>
      </Card>
      <Card className="order-2 h-fit w-full max-w-56 shrink-0 gap-2 overflow-hidden py-0 xl:sticky xl:top-4 xl:order-3 xl:w-56">
        <div className="flex aspect-[3/4] items-center justify-center bg-muted">
          {/* always the player's own photo (user's decision, 26/10), also while browsing faces of a pack */}
          {player.photo ? (
            <img src={photoPreviewUrl(player.photo)} alt="" className="size-full object-contain" />
          ) : (
            <User className="size-16 text-muted-foreground/50" />
          )}
        </div>
        <p className="px-4 pb-3 text-center text-xs text-muted-foreground">
          {player.photo ? t('playerEdit.photoReference') : t('playerEdit.noPhoto')}
        </p>
      </Card>
    </div>
  )
}

export function PlayerEditPage() {
  const { t } = useI18n()
  const { uid } = useParams()
  const { draft, removePlayer } = useProject()
  const navigate = useNavigate()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [baseOpen, setBaseOpen] = useState(false)
  const hasBase = !!useStatus().data?.config.players_base_file
  const { copyPlayer } = useCopy()
  const player = draft.players.find((p) => p.uid === uid)
  const team = player?.team ? draft.teams.find((tm) => tm.uid === player.team) : undefined

  const back = useBack(
    team ? { to: `/teams/${team.uid}`, label: team.name || t('players.colTeam') } : { to: '/players', label: t('nav.players') },
  )
  const goBack = useGoBack()
  const keepBack = useKeepBack()
  const tabs = useTabParam('data')

  if (!player) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        <p className="text-muted-foreground">{t('playerEdit.notFound')}</p>
      </div>
    )
  }

  const name = player.display_name || `${player.first_name} ${player.last_name}`.trim()
  return (
    <div className="max-w-7xl space-y-4">
      <BackButton back={back} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <PlayerAvatar player={player} className="size-10" />
          <h1 className="text-2xl font-semibold">{name || t('players.new')}</h1>
          <EntityIssues uid={player.uid} />
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!hasBase}
            title={hasBase ? t('playerEdit.baseHint') : t('apiError.players_base_not_set')}
            onClick={() => setBaseOpen(true)}
          >
            <DatabaseZap /> {t('base.title')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            title={t('playerEdit.copyHint')}
            onClick={async () => {
              const copied = await copyPlayer(player.uid)
              if (copied) navigate(`/players/${copied}`, keepBack)
            }}
          >
            <Copy /> {t('common.copy')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)}>
            <Trash2 /> {t('playerEdit.delete')}
          </Button>
        </div>
      </div>
      <BaseDataDialog player={player} open={baseOpen} onOpenChange={setBaseOpen} />
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('teamEdit.tabData')}</TabsTrigger>
          <TabsTrigger value="skills">{t('base.skills')}</TabsTrigger>
          <TabsTrigger value="appearance">{t('playerEdit.tabLook')}</TabsTrigger>
        </TabsList>
        <TabsContent value="data">
          <DataTab player={player} />
        </TabsContent>
        <TabsContent value="skills">
          <SkillsTab player={player} />
        </TabsContent>
        <TabsContent value="appearance">
          <AppearanceTab player={player} />
        </TabsContent>
      </Tabs>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('teamEdit.deleteTitle', { name: name || t('playerEdit.thePlayer') })}</AlertDialogTitle>
            <AlertDialogDescription>{t('playerEdit.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removePlayer(player.uid)
                goBack(back)
              }}
            >
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
