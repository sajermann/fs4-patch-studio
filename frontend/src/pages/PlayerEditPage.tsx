import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Copy, DatabaseZap, Dices, Eraser, Info, LoaderCircle, RotateCcw, Trash2, User } from 'lucide-react'
import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import type { View as PreviewView } from '@/components/common/PlayerPreview'
import { api, ApiError, photoPreviewUrl, scannedFaceQuery, type FaceSource } from '@/api/client'
import { HAIR_MODES, HAIR_THICKNESS, THICK_HAIR_MODES, type HairMode, type Player } from '@/api/types'
import { THUMBNAIL_CODES, ThumbnailField, ThumbnailPicker } from '@/components/common/AppearanceThumbnails'
import { BaseDataDialog } from '@/components/common/BaseDataDialog'
import { FacePicker, type BrowsedFace } from '@/components/common/FacePicker'
import { EntityIssues, Field, NumberInput, OriginalBadge, Stepper } from '@/components/common/form'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
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
import { BUILDS, bodyCode, buildOf, heightClass } from '@/lib/body'
import { useI18n, type MessageKey, type TFunction } from '@/i18n'
import { useCopy } from '@/lib/copy'
import { APPEARANCE_LABELS, FOOT_LABELS, SKILL_LABELS } from '@/lib/labels'
import { computeOverall } from '@/lib/skills'
import { GOALKEEPER_POSITION, backName, previewAppearance, teamPreviewKit } from '@/lib/preview'
import { useEntryOfPath } from '@/lib/members'
import { linkedTeam, teamKey, teamPath } from '@/lib/players'
import { PlayerBoots } from '@/components/common/PlayerBoots'
import { PlayerGloves } from '@/components/common/PlayerGloves'
import { preferredPosition } from '@/lib/gloves'
import { PlayerTeamsCard } from '@/components/common/PlayerTeams'
import { cn } from '@/lib/utils'
import { usePlayerDefaults, useProject, useWasEdited } from '@/state/project'
import { useCatalog, useLookups, useStatus } from '@/state/queries'

const PlayerPreview = lazy(() => import('@/components/common/PlayerPreview'))

const NONE = 'none'
// the Visual card's second group; the rest of its fields are the face
const BODY_CODES = ['bodytypecode', 'jerseysleevelengthcode', 'socklengthcode']
const LOOK_MIN_HEIGHT = 360
const LOOK_BOTTOM_GAP = 16
// codes that still matter with a real face: the scalp hair color (painted by the converter), the body skin and the body
const FACE_MODE_CODES = ['haircolorcode', 'skintonecode', 'bodytypecode', 'shoetypecode', 'gkglovetypecode', 'jerseysleevelengthcode', 'socklengthcode']
const FACE_MODE_LABELS: Record<string, MessageKey> = { haircolorcode: 'playerEdit.faceHairColor', skintonecode: 'playerEdit.faceSkinTone' }
/** Options of a real face (ScannedFace) being looked at, before "use this face". */
type BrowseFaceOptions = { paint_scalp: boolean; hair_mode: HairMode; hair_thickness: number }
// new faces: scalp paint off (user's decision, 06/11/2026: it helps few faces and stains others)
const NEW_FACE_OPTIONS: BrowseFaceOptions = { paint_scalp: false, hair_mode: 'standard', hair_thickness: HAIR_THICKNESS.default }
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
  const { updatePlayer } = useProject()
  const catalog = useCatalog().data
  const lookups = useLookups()
  const defaults = usePlayerDefaults(player.uid)
  const set = (patch: Partial<Player>) => updatePlayer(player.uid, patch)
  const [hMin, hMax] = catalog?.ranges.height ?? [150, 277]
  const [wMin, wMax] = catalog?.ranges.weight ?? [40, 167]
  const nationality = player.fields.nationality

  return (
    <div className="space-y-4">
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
          <PreferredPosition player={player} />
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
    <PlayerTeamsCard player={player} />
    </div>
  )
}

/** The player's preferred position, worked out by the app (lib/gloves preferredPosition) and never typed: GK when a
 * glove is picked (only goalkeepers wear their own glove), otherwise his most common position in his teams. */
function PreferredPosition({ player }: { player: Player }) {
  const { t } = useI18n()
  const lookups = useLookups()
  const { position, byGlove } = preferredPosition(player)
  return (
    <div className="space-y-1.5">
      <Label>{t('playerEdit.preferredPosition')}</Label>
      <p className="flex h-9 items-center gap-1.5 text-sm">
        <span className="font-medium">{lookups.position.get(position) ?? position}</span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className={cn('size-4 shrink-0', byGlove ? 'text-amber-600 dark:text-amber-500' : 'text-muted-foreground')} />
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{t(byGlove ? 'playerEdit.preferredPositionGlove' : 'playerEdit.preferredPositionHint')}</TooltipContent>
        </Tooltip>
      </p>
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
          <Button variant="ghost" size="sm" onClick={() =>
              updatePlayer(player.uid, {
                // an original player goes back to the game's own bars; a new one to its template's
                skills: player.original_id != null ? { ...(player.loaded?.player.skills as Record<string, number>) } : withOverall({}),
              })
            }>
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

/** Height that takes an element from where it starts to the end of the viewport (a small gap below it). */
function useHeightToViewportEnd() {
  const ref = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    const measure = () => {
      if (ref.current) setHeight(Math.max(LOOK_MIN_HEIGHT, window.innerHeight - ref.current.getBoundingClientRect().top - LOOK_BOTTOM_GAP))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])
  return { ref, height }
}

function AppearanceTab({ player }: { player: Player }) {
  const { t } = useI18n()
  const { draft, updatePlayer } = useProject()
  const catalog = useCatalog().data
  const options = catalog?.appearance ?? {}
  const defaults = usePlayerDefaults(player.uid)
  // the pictures of a code in place of this card: the clicked one shows in the preview until Apply or Cancel
  const [picking, setPicking] = useState<{ code: string; start: number | undefined; value: number | undefined } | null>(null)
  useEffect(() => setPicking(null), [player.uid])
  // a player with no team has no template player to inherit from: he stays on the first option, as the preview shows him
  const inheritedCode = (code: string): number | undefined => defaults?.appearance[code] ?? options[code]?.[0]
  const shownPlayer = picking?.value === undefined ? player : { ...player, appearance: { ...player.appearance, [picking.code]: picking.value } }
  const preview = previewAppearance(shownPlayer, defaults, catalog, draft.boots, draft.gloves)
  const [browsing, setBrowsingFace] = useState<BrowsedFace | null>(null)
  // options of the face being looked at: shown and previewed at once, set on the player only by "use this face"
  const [browseOptions, setBrowseOptions] = useState<BrowseFaceOptions>(NEW_FACE_OPTIONS)
  const [browseHair, setBrowseHair] = useState<{ key: string; code: number } | null>(null)
  // touching a face option shows the Face view, a body option the Body view (PlayerPreview viewRequest)
  const [viewRequest, setViewRequest] = useState<{ view: PreviewView; seq: number }>()
  const showView = (view: PreviewView) => setViewRequest((r) => ({ view, seq: (r?.seq ?? 0) + 1 }))
  // with a real face the skin tone colors only the body (the face brings its own skin): it goes with the body options
  const isBodyCode = (code: string) => BODY_CODES.includes(code) || (!player.generic && code === 'skintonecode')
  const viewOf = (code: string): PreviewView => (isBodyCode(code) ? 'body' : 'face')
  const setBrowsing = (face: BrowsedFace | null) => {
    if (face) showView('face')
    setBrowsingFace(face)
    if (!face) {
      setBrowseOptions(NEW_FACE_OPTIONS)
      setBrowseHair(null)
    }
  }
  const generic = player.generic
  // the converter paints the scalp with the player's hair color (fsmod.scanface)
  const playerHairColor = shownPlayer.appearance.haircolorcode ?? inheritedCode('haircolorcode') ?? 0
  const faceSource: FaceSource | null = browsing
    ? { folder: browsing.folder, face: browsing.face.id }
    : !generic && player.face
      ? { player: player.uid, face: player.face.source_id }
      : null
  // hair color suggested from the looked-at face's own hair (the user can still change it)
  const browseKey = browsing ? `${browsing.folder}|${browsing.face.id}` : ''
  const hairSuggestion = useQuery({
    queryKey: ['face-hair-color', browseKey],
    queryFn: () => api.faceHairColor(faceSource as FaceSource),
    enabled: !!browsing,
    retry: false,
    staleTime: Infinity,
  })
  const browseHairColor = browsing
    ? browseHair?.key === browseKey
      ? browseHair.code
      : (hairSuggestion.data?.haircolorcode ?? undefined)
    : undefined
  const hairColorCode = (picking?.code === 'haircolorcode' ? picking.value : undefined) ?? browseHairColor ?? playerHairColor
  const faceOptions: BrowseFaceOptions = browsing
    ? browseOptions
    : {
        paint_scalp: player.face?.paint_scalp ?? true,
        hair_mode: player.face?.hair_mode ?? 'standard',
        hair_thickness: player.face?.hair_thickness ?? HAIR_THICKNESS.default,
      }
  const setFaceOption = (patch: Partial<BrowseFaceOptions>) => {
    showView('face')
    if (browsing) setBrowseOptions((o) => ({ ...o, ...patch }))
    else if (player.face) updatePlayer(player.uid, { face: { ...player.face, ...patch } })
  }
  const showFaceOptions = !!browsing || !!player.face
  const paintScalp = faceOptions.paint_scalp
  const hairMode = faceOptions.hair_mode
  const thickHair = THICK_HAIR_MODES.includes(hairMode)
  const hairThickness = faceOptions.hair_thickness
  // an original player who keeps the game's scanned head: that head as it is
  const original = player.original_id != null
  const gameHead = original && player.loaded?.player.generic === false
  const scanned = faceSource
    ? { query: scannedFaceQuery(faceSource, hairColorCode, paintScalp, hairMode, thickHair ? hairThickness : undefined) }
    : !generic && gameHead
      ? { base: `/api/preview/game-head/${player.original_id}`, query: '' }
      : null
  const faceQuery = faceSource ? scanned?.query : undefined
  const faceCheck = useQuery({
    queryKey: ['scanned-check', faceQuery],
    queryFn: () => api.checkScannedFace(faceQuery as string),
    enabled: !!faceQuery,
    retry: false,
    staleTime: Infinity,
  })
  const faceUnsupported = !!faceQuery && faceCheck.error instanceof ApiError && faceCheck.error.code === 'face_unsupported'
  // Team Home kit of the player's team (the goalkeeper kit for a goalkeeper; neutral grey for free agents)
  const link = player.teams.find((l) => linkedTeam(draft, l.team)) ?? player.teams[0]
  const team = link && linkedTeam(draft, link.team)
  const inherited = link && defaults?.team === link.team ? defaults : undefined
  const kit = teamPreviewKit(team, (link?.position ?? inherited?.position) === GOALKEEPER_POSITION ? 'goalkeeper' : 'home', {
    number: link?.number ?? inherited?.number,
    name: backName(player),
  })
  const set = (code: string, value: number | undefined) => {
    showView(viewOf(code))
    const appearance = { ...player.appearance }
    if (value === undefined) delete appearance[code]
    else appearance[code] = value
    updatePlayer(player.uid, { appearance })
  }
  const lookCard = useHeightToViewportEnd()
  // body type: the user picks the build, the height (Data tab) picks the class (lib/body)
  const playerHeight = player.height ?? defaults?.height ?? 180
  const bodyClass = heightClass(playerHeight)
  const ownBody = player.appearance.bodytypecode
  const inheritedBody = inheritedCode('bodytypecode')
  const bodyLabel = (code: number) => `${t(`playerEdit.heightClass.${bodyClass}`)} · ${t(`playerEdit.build.${BUILDS[buildOf(code)]}`)}`
  const lookingHairColor = (code: string) => !!browsing && code === 'haircolorcode'
  // hair and beard pictures come in the color the player has
  const thumbnailVariant = (code: string) =>
    code === 'hairtypecode' ? hairColorCode : code === 'facialhairtypecode' ? (shownPlayer.appearance.facialhaircolorcode ?? inheritedCode('facialhaircolorcode') ?? 0) : 0
  const openPicker = (code: string) => {
    showView(viewOf(code))
    const start = lookingHairColor(code) ? hairColorCode : (player.appearance[code] ?? inheritedCode(code))
    setPicking({ code, start, value: start })
  }
  const applyPick = () => {
    if (!picking) return
    if (lookingHairColor(picking.code)) {
      if (picking.value !== undefined) setBrowseHair({ key: browseKey, code: picking.value })
    } else set(picking.code, picking.value)
    setPicking(null)
  }
  const fieldLabel = (code: string) => t((!generic && FACE_MODE_LABELS[code]) || APPEARANCE_LABELS[code])
  const randomize = () => {
    showView('face')
    const appearance: Record<string, number> = {}
    for (const code of ['headtypecode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'facialhairtypecode', 'eyecolorcode']) {
      const list = catalog?.appearance_natural?.[code] ?? options[code] ?? []
      if (list.length) appearance[code] = list[Math.floor(Math.random() * list.length)]
    }
    updatePlayer(player.uid, { appearance: { ...player.appearance, ...appearance } })
  }

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <div
        ref={lookCard.ref}
        style={{ '--look-height': `${lookCard.height}px` } as CSSProperties}
        className="order-3 w-[420px] max-w-full xl:order-1 xl:h-(--look-height) xl:shrink-0"
      >
      <Card className="h-full">
        {picking ? (
          <ThumbnailPicker
            key={picking.code}
            code={picking.code}
            title={fieldLabel(picking.code)}
            options={options[picking.code] ?? []}
            groups={picking.code === 'hairtypecode' ? catalog?.hair_groups.map((g) => ({ ...g, label: t(`playerEdit.hairGroup.${g.key}`) })) : undefined}
            value={picking.value}
            variant={thumbnailVariant(picking.code)}
            changed={picking.value !== picking.start}
            onSelect={(value) => setPicking({ ...picking, value })}
            onApply={applyPick}
            onCancel={() => setPicking(null)}
          />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-(--card-spacing) overflow-y-auto">
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
            <Button
              variant="ghost"
              size="sm"
              onClick={() => updatePlayer(player.uid, { appearance: original ? { ...(player.loaded?.player.appearance as Record<string, number>) } : {} })}
            >
              <Eraser /> {t('playerEdit.resetDefault')}
            </Button>
          </div>
        </CardHeader>
        {!generic && (
          <CardContent>
            {gameHead && (
              <div className="mb-3 flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
                <span>{player.face ? t('playerEdit.gameHeadReplaced') : t('playerEdit.gameHead')}</span>
                {player.face && (
                  <Button variant="outline" size="sm" onClick={() => updatePlayer(player.uid, { face: undefined })}>
                    {t('playerEdit.gameHeadBack')}
                  </Button>
                )}
              </div>
            )}
            <FacePicker
              key={player.uid}
              player={player}
              browsing={browsing}
              onBrowse={setBrowsing}
              unsupported={faceUnsupported}
              pickExtras={{
                face: browseOptions,
                ...(browseHairColor !== undefined && { appearance: { haircolorcode: browseHairColor } }),
              }}
            />
            {browsing && <p className="mt-3 text-xs text-muted-foreground">{t('playerEdit.faceOptionsPending')}</p>}
            {showFaceOptions && (
              <label className="mt-3 flex items-start gap-2 text-sm">
                <Checkbox
                  className="mt-0.5"
                  checked={paintScalp}
                  onCheckedChange={(v) => setFaceOption({ paint_scalp: v === true })}
                />
                <span>
                  {t('playerEdit.paintScalp')}
                  <span className="block text-xs text-muted-foreground">{t('playerEdit.paintScalpHint')}</span>
                </span>
              </label>
            )}
            {showFaceOptions && (
              <div className="mt-3 grid gap-1.5 text-sm">
                <Label>{t('playerEdit.hairMode')}</Label>
                <Select
                  value={hairMode}
                  onValueChange={(v) => setFaceOption({ hair_mode: v as HairMode })}
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
            {showFaceOptions && thickHair && (
              <HairThickness
                value={hairThickness}
                onCommit={(v) => setFaceOption({ hair_thickness: v })}
              />
            )}
          </CardContent>
        )}
        {[
          { title: t('playerEdit.lookGroupFace'), body: false },
          { title: t('playerEdit.lookGroupBody'), body: true },
        ].map(({ title, body }) => (
        <CardContent key={title} className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
          <h3 className="border-b pb-1 text-sm font-semibold text-muted-foreground sm:col-span-2">{title}</h3>
          {Object.keys(APPEARANCE_LABELS)
            // boots: Accessories tab (one per pitch surface)
            // boots and the goalkeeper glove: Accessories tab
            .filter((code) => !['shoetypecode', 'gkglovetypecode'].includes(code) && options[code] && (generic || FACE_MODE_CODES.includes(code)))
            .filter((code) => isBodyCode(code) === body)
            .map((code) => (
              <Field
                key={code}
                label={fieldLabel(code)}
                entity={player.uid}
                field={`appearance.${code}`}
                help={code === 'bodytypecode' ? t('playerEdit.bodyTypeHint') : undefined}
              >
                {code === 'bodytypecode' ? (
                  <Stepper
                    value={ownBody === undefined ? undefined : bodyCode(buildOf(ownBody), playerHeight)}
                    options={BUILDS.map((_, build) => bodyCode(build, playerHeight))}
                    onChange={(v) => set(code, v)}
                    inherited={inheritedBody === undefined ? undefined : bodyCode(buildOf(inheritedBody), playerHeight)}
                    label={bodyLabel}
                    wide
                  />
                ) : THUMBNAIL_CODES.includes(code) ? (
                  <ThumbnailField
                    code={code}
                    /* looking at a real face: its hair color is kept here until "use this face" */
                    value={lookingHairColor(code) ? hairColorCode : player.appearance[code]}
                    inherited={lookingHairColor(code) ? (hairSuggestion.data?.haircolorcode ?? undefined) : inheritedCode(code)}
                    options={options[code]}
                    variant={thumbnailVariant(code)}
                    onOpen={() => openPicker(code)}
                  />
                ) : (
                  <Stepper
                    value={player.appearance[code]}
                    options={options[code]}
                    onChange={(v) => set(code, v)}
                    inherited={inheritedCode(code)}
                  />
                )}
              </Field>
            ))}
        </CardContent>
        ))}
          </div>
        )}
      </Card>
      </div>
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
            {catalog &&
              (faceUnsupported && faceSource ? (
                <div className="flex size-full flex-col items-center justify-center gap-2 p-6 text-center">
                  <AlertTriangle className="size-8 text-destructive" />
                  <p className="font-medium">{t('faces.unsupportedTitle')}</p>
                  <p className="text-sm text-muted-foreground">{t('faces.unsupported', { id: faceSource.face })}</p>
                  {faceCheck.error instanceof ApiError && faceCheck.error.error && (
                    <p className="font-mono text-xs break-all text-muted-foreground">{faceCheck.error.error}</p>
                  )}
                </div>
              ) : (
                <PlayerPreview
                  appearance={preview}
                  outfit={{ kind: 'team', kit }}
                  face={scanned}
                  viewRequest={viewRequest}
                  closeUpOnly={!!draft.game_patches?.close_up_heads}
                />
              ))}
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
  const { uid: param } = useParams()
  const { draft, removePlayer, updatePlayer } = useProject()
  const navigate = useNavigate()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [baseOpen, setBaseOpen] = useState(false)
  const hasBase = !!useStatus().data?.config.players_base_file
  const { copyPlayer } = useCopy()
  const { entry: player, loading } = useEntryOfPath<Player>('player', param)
  const uid = player?.uid
  const team = player?.teams.map((l) => linkedTeam(draft, l.team)).find((tm) => tm)

  const back = useBack(
    team ? { to: teamPath(teamKey(team)), label: team.name || t('players.colTeam') } : { to: '/players', label: t('nav.players') },
  )
  const goBack = useGoBack()
  const keepBack = useKeepBack()
  const tabs = useTabParam('data')
  const edited = useWasEdited(uid)

  if (!player) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {loading ? (
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <p className="text-muted-foreground">{t('playerEdit.notFound')}</p>
        )}
      </div>
    )
  }

  const name = player.display_name || `${player.first_name} ${player.last_name}`.trim()
  const original = player.original_id != null
  return (
    <div className="max-w-7xl space-y-4">
      <BackButton back={back} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <PlayerAvatar player={player} className="size-10" />
          <h1 className="text-2xl font-semibold">{name || t('players.new')}</h1>
          {original && <OriginalBadge entry={player.uid} />}
          {!original && player.hidden && <OutOfPatchBadge alert />}
          <EntityIssues uid={player.uid} />
        </div>
        <div className="flex gap-2">
          {!original && (
            <HideButton
              variant="outline"
              hidden={!!player.hidden}
              onToggle={() => updatePlayer(player.uid, { hidden: !player.hidden })}
              hideHint={t('players.hideHint')}
              showHint={t('players.showHint')}
            />
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={!hasBase}
            title={hasBase ? t('playerEdit.baseHint') : t('apiError.players_base_not_set')}
            onClick={() => setBaseOpen(true)}
          >
            <DatabaseZap /> {t('base.title')}
          </Button>
          {!original && (
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
          )}
          <Button
            variant="outline"
            size="sm"
            title={original ? t(edited ? 'playerEdit.restoreOriginalHint' : 'common.unchangedHint') : undefined}
            disabled={original && !edited}
            onClick={() => setDeleteOpen(true)}
          >
            {original ? <RotateCcw /> : <Trash2 />} {original ? t('teamEdit.restoreOriginal') : t('playerEdit.delete')}
          </Button>
        </div>
      </div>
      <BaseDataDialog player={player} open={baseOpen} onOpenChange={setBaseOpen} />
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('teamEdit.tabData')}</TabsTrigger>
          <TabsTrigger value="skills">{t('base.skills')}</TabsTrigger>
          <TabsTrigger value="appearance">{t('playerEdit.tabLook')}</TabsTrigger>
          <TabsTrigger value="accessories">{t('playerEdit.tabAccessories')}</TabsTrigger>
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
        <TabsContent value="accessories">
          <div className="space-y-4">
            <PlayerBoots key={player.uid} player={player} />
            <PlayerGloves key={`g-${player.uid}`} player={player} />
          </div>
        </TabsContent>
      </Tabs>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t(original ? 'teamEdit.restoreOriginalTitle' : 'teamEdit.deleteTitle', { name: name || t('playerEdit.thePlayer') })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {original ? t('playerEdit.restoreOriginalDescription') : t('playerEdit.deleteDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                removePlayer(player.uid)
                if (!original) goBack(back) // restored: the page stays and loads him again from the game
              }}
            >
              {original ? t('teamEdit.restoreOriginal') : t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
