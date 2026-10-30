import { Copy, Loader2, RotateCcw, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, imageUrl, kitPreviewUrl } from '@/api/client'
import type { KitKind, KitPart, RGB, Team } from '@/api/types'
import { ColorInput, EntityIssues, Field, FieldIssues, OriginalBadge } from '@/components/common/form'
import { LineupEditor, type LineupPlayer } from '@/components/common/LineupEditor'
import { RosterCard } from '@/components/common/Roster'
import { TeamLeagues } from '@/components/common/TeamLeagues'
import { useEntryOfPath, useTeamMembers } from '@/lib/members'
import { RealKitEditor } from '@/components/common/RealKitEditor'
import { StreetKitEditor } from '@/components/common/StreetKitEditor'
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
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BackButton, useBack, useGoBack, useKeepBack, useTabParam } from '@/lib/back'
import { useI18n } from '@/i18n'
import { useCopy } from '@/lib/copy'
import { KIT_LABELS, KIT_PART_LABELS } from '@/lib/labels'
import { fullKit } from '@/lib/teams'
import { cn } from '@/lib/utils'
import { useIssues, useProject, useWasEdited } from '@/state/project'

function DataTab({ team }: { team: Team }) {
  const { t } = useI18n()
  const { updateTeam } = useProject()
  const set = (patch: Partial<Team>) => updateTeam(team.uid, patch)
  const text = (key: 'short_name' | 'name_10' | 'name_7' | 'abbreviation', label: string, fallback: string) => (
    <Field label={label} entity={team.uid} field={key}>
      <Input value={team[key] ?? ''} placeholder={fallback} onChange={(e) => set({ [key]: e.target.value || undefined })} />
    </Field>
  )
  return (
    <Card>
      <CardContent className="grid gap-4 pt-6 sm:grid-cols-2">
        <Field label={t('teamEdit.fullName')} entity={team.uid} field="name" className="sm:col-span-2">
          <Input value={team.name} onChange={(e) => set({ name: e.target.value })} autoFocus={!team.name} />
        </Field>
        {text('short_name', t('leagueEdit.shortName'), team.name)}
        {text('name_10', t('teamEdit.name10'), team.name.slice(0, 10))}
        {text('name_7', t('teamEdit.name7'), team.name.slice(0, 7))}
        {text('abbreviation', t('teamEdit.abbreviation'), team.name.slice(0, 3).toUpperCase())}
      </CardContent>
    </Card>
  )
}

function CrestTab({ team }: { team: Team }) {
  const { t } = useI18n()
  const { updateTeam } = useProject()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const crestIssues = useIssues(team.uid, 'crest')
  const set = (patch: Partial<Team>) => updateTeam(team.uid, patch)

  const upload = async (file: File) => {
    setUploading(true)
    try {
      const r = await api.uploadImage(file)
      set({ crest: r.path })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('image.uploadFailed'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>{t('teamEdit.crest')}</CardTitle>
          <CardDescription>{t('teamEdit.crestDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div
            className="flex h-48 cursor-pointer items-center justify-center rounded-lg border border-dashed bg-[repeating-conic-gradient(var(--muted)_0_25%,transparent_0_50%)] bg-[length:16px_16px]"
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
            ) : team.crest ? (
              <img src={imageUrl(team.crest)} alt={t('teamEdit.crest')} className="max-h-40 max-w-full object-contain" />
            ) : (
              <span className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                <Upload /> {t('image.clickOrDrop')}
              </span>
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
          <FieldIssues issues={crestIssues} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t('teamEdit.colors')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label={t('teamEdit.primaryColor')} entity={team.uid} field="primary_color">
            <ColorInput value={team.primary_color} onChange={(v) => set({ primary_color: v })} />
          </Field>
          <Field label={t('teamEdit.secondaryColor')} entity={team.uid} field="secondary_color">
            <ColorInput value={team.secondary_color} onChange={(v) => set({ secondary_color: v })} />
          </Field>
        </CardContent>
      </Card>
    </div>
  )
}

function KitsTab({ team }: { team: Team }) {
  const { t } = useI18n()
  const { updateTeam } = useProject()
  const setPart = (kind: KitKind, part: KitPart, value: RGB) =>
    updateTeam(team.uid, { kits: { ...team.kits, [kind]: { ...team.kits[kind], [part]: value } } })
  const reset = (kind: KitKind) => {
    const kits = { ...team.kits }
    delete kits[kind]
    updateTeam(team.uid, { kits })
  }
  const real = team.use_real_kits ?? false
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t('teamEdit.teamKits')}</CardTitle>
          <div className="flex w-fit rounded-md border p-0.5 text-sm">
            {([false, true] as const).map((r) => (
              <button
                key={String(r)}
                type="button"
                onClick={() => updateTeam(team.uid, { use_real_kits: r })}
                className={cn('rounded px-3 py-1', real === r ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              >
                {r ? t('teamEdit.kitsReal') : t('teamEdit.kitsGeneric')}
              </button>
            ))}
          </div>
          <CardDescription>
            {real ? t('teamEdit.kitsRealDescription') : t('teamEdit.kitsGenericDescription')}
          </CardDescription>
        </CardHeader>
      </Card>
      {real ? (
        <RealKitEditor team={team} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {(['home', 'away'] as KitKind[]).map((kind) => {
            const kit = fullKit(team, kind)
            return (
              <Card key={kind}>
                <CardHeader>
                  <CardTitle>{t('teamEdit.teamKit', { kind: t(KIT_LABELS[kind]) })}</CardTitle>
                  <CardDescription>{t('teamEdit.teamKitDescription')}</CardDescription>
                  <CardAction>
                    {team.kits[kind] && (
                      <Button variant="ghost" size="sm" onClick={() => reset(kind)}>
                        <RotateCcw /> {t('street.reset')}
                      </Button>
                    )}
                  </CardAction>
                </CardHeader>
                <CardContent className="flex gap-6">
                  <div className="space-y-3">
                    {(Object.keys(KIT_PART_LABELS) as KitPart[]).map((part) => (
                      <Field key={part} label={t(KIT_PART_LABELS[part])} entity={team.uid} field={`kits.${kind}.${part}`}>
                        <ColorInput value={kit[part]} onChange={(v) => setPart(kind, part, v)} />
                      </Field>
                    ))}
                  </div>
                  <div className="flex flex-1 flex-col items-center justify-center rounded-lg bg-muted/50 p-2">
                    <img src={kitPreviewUrl(kit.jersey, team.crest)} alt={t('teamEdit.kitThumbnail')} className="w-40" />
                    <span className="text-xs text-muted-foreground">{t('teamEdit.kitThumbnailHint')}</span>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
      <StreetKitEditor team={team} />
    </div>
  )
}

function LineupTab({ team }: { team: Team }) {
  const players: LineupPlayer[] = useTeamMembers(team)
    .filter((m) => !m.hidden)
    .map((m) => ({ ref: m.ref, name: m.name, position: m.position, avatar: m.avatar }))
  return <LineupEditor team={team} players={players} />
}

export function TeamEditPage() {
  const { t } = useI18n()
  const { uid: param } = useParams()
  const { removeTeam } = useProject()
  const navigate = useNavigate()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)
  const copy = useCopy()
  const { entry: team, loading } = useEntryOfPath<Team>('team', param)
  const uid = team?.uid
  const back = useBack({ to: '/teams', label: t('nav.teams') })
  const goBack = useGoBack()
  const keepBack = useKeepBack()
  const tabs = useTabParam('data')
  const original = team?.original_id != null
  const edited = useWasEdited(uid, team?.original_id)

  const copyTeam = async (withRoster: boolean) => {
    setCopyOpen(false)
    const copied = team && (await copy.copyTeam(team.uid, withRoster))
    if (copied) {
      toast.success(withRoster ? t('teamEdit.copiedWithRoster') : t('teamEdit.copied'))
      navigate(`/teams/${copied}`, keepBack)
    }
  }

  if (!team) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {loading ? (
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <p className="text-muted-foreground">{t('issue.team_not_found')}</p>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-5xl space-y-4">
      <BackButton back={back} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {team.crest && <img src={imageUrl(team.crest)} alt="" className="size-10 object-contain" />}
          <h1 className="text-2xl font-semibold">{team.name || t('teams.new')}</h1>
          {original && <OriginalBadge entry={team.uid} team={team.original_id} />}
          <EntityIssues uid={team.uid} />
        </div>
        <div className="flex gap-2">
          {!original && (
            <Button
              variant="outline"
              size="sm"
              disabled={!copy.canCopyTeam(team.uid)}
              title={
                copy.canCopyTeam(team.uid) ? t('teamEdit.copyHint') : t('teamEdit.copyMax', { max: copy.maxLeagueTeams })
              }
              onClick={() => setCopyOpen(true)}
            >
              <Copy /> {t('common.copy')}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            title={original ? t(edited ? 'teamEdit.restoreOriginalHint' : 'common.unchangedHint') : undefined}
            disabled={original && !edited}
            onClick={() => setDeleteOpen(true)}
          >
            {original ? <RotateCcw /> : <Trash2 />} {original ? t('teamEdit.restoreOriginal') : t('teamEdit.delete')}
          </Button>
        </div>
      </div>
      <Tabs {...tabs}>
        <TabsList>
          <TabsTrigger value="data">{t('teamEdit.tabData')}</TabsTrigger>
          <TabsTrigger value="crest">{t('teamEdit.tabCrest')}</TabsTrigger>
          <TabsTrigger value="kits">{t('teamEdit.tabKits')}</TabsTrigger>
          <TabsTrigger value="roster">{t('teamEdit.roster')}</TabsTrigger>
          <TabsTrigger value="lineup">{t('lineup.tab')}</TabsTrigger>
        </TabsList>
        <TabsContent value="data" className="space-y-4">
          <DataTab team={team} />
          <TeamLeagues team={team} />
        </TabsContent>
        <TabsContent value="crest">
          <CrestTab team={team} />
        </TabsContent>
        <TabsContent value="kits">
          <KitsTab team={team} />
        </TabsContent>
        <TabsContent value="roster">
          <RosterCard team={team} />
        </TabsContent>
        <TabsContent value="lineup">
          <LineupTab team={team} />
        </TabsContent>
      </Tabs>
      <Dialog open={copyOpen} onOpenChange={setCopyOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('teamEdit.copyTitle', { name: team.name || t('teamEdit.theTeam') })}</DialogTitle>
            <DialogDescription>{t('teamEdit.copyDescription')}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => copyTeam(false)}>
              {t('teamEdit.copyTeamOnly')}
            </Button>
            <Button onClick={() => copyTeam(true)}>{t('teamEdit.copyWithRoster')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t(original ? 'teamEdit.restoreOriginalTitle' : 'teamEdit.deleteTitle', {
                name: team.name || t('teamEdit.theTeam'),
              })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {original ? t('teamEdit.restoreOriginalDescription') : t('teamEdit.deleteDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                if (team.original_id != null) {
                  // the game's squad comes back too (who left returns, who joined leaves)
                  try {
                    removeTeam(team.uid, await api.originalSquad(team.original_id))
                  } catch (e) {
                    toast.error(e instanceof ApiError ? e.message : t('teamEdit.restoreFailed'))
                    return
                  }
                } else {
                  removeTeam(team.uid)
                }
                goBack(back)
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
