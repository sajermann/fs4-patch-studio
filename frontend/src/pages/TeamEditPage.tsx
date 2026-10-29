import { Copy, Loader2, Plus, RotateCcw, Trash2, Upload, UserMinus, UserPlus } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, imageUrl, kitPreviewUrl } from '@/api/client'
import type { KitKind, KitPart, RGB, Team } from '@/api/types'
import { ColorInput, EntityIssues, Field, FieldIssues, NumberInput, OriginalBadge } from '@/components/common/form'
import { OutOfPatchBadge } from '@/components/common/HideButton'
import { LineupEditor, type LineupPlayer } from '@/components/common/LineupEditor'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { RealKitEditor } from '@/components/common/RealKitEditor'
import { StreetKitEditor } from '@/components/common/StreetKitEditor'
import { RoleCells, RoleHeads, TakersCard } from '@/components/common/TakersCard'
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
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BackButton, useBack, useFrom, useGoBack, useKeepBack, useTabParam } from '@/lib/back'
import { useI18n } from '@/i18n'
import { useCopy } from '@/lib/copy'
import { KIT_LABELS, KIT_PART_LABELS } from '@/lib/labels'
import { lineupsWithout, takersWithout } from '@/lib/lineup'
import { effectiveRoles, fullKit, useLeagueTeams } from '@/lib/teams'
import { cn } from '@/lib/utils'
import { newUid, useIssues, useProject } from '@/state/project'
import { useCatalog, useLookups, useOriginalLeagues, useOriginalPlayers, useOriginalTeams } from '@/state/queries'

const AUTO = 'auto'

/** League dropdown: the project's new leagues + the original leagues the selector shows. */
export function LeagueSelect({ value, onChange }: { value: number | string; onChange: (v: number | string) => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const originals = (useOriginalLeagues().data ?? []).filter((l) => !l.hidden || l.id === value)
  const leagueTeams = useLeagueTeams()
  // a full league can't take one more team (its current one stays selectable)
  const full = (league: number | string) => league !== value && leagueTeams.isFull(league)
  const fullHint = ` ${t('teamEdit.leagueFull', { max: leagueTeams.max })}`
  const encode = (v: number | string) => (typeof v === 'string' ? `new:${v}` : `orig:${v}`)
  return (
    <Select value={encode(value)} onValueChange={(v) => onChange(v.startsWith('new:') ? v.slice(4) : Number(v.slice(5)))}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {draft.leagues.length > 0 && (
          <SelectGroup>
            <SelectLabel>{t('teams.newLeagues')}</SelectLabel>
            {draft.leagues.map((l) => (
              <SelectItem key={l.uid} value={encode(l.uid)} disabled={full(l.uid)}>
                {l.name || t('league.unnamed')}
                {full(l.uid) && fullHint}
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        <SelectGroup>
          <SelectLabel>{t('teams.originalLeagues')}</SelectLabel>
          {originals.map((l) => (
            <SelectItem key={l.id} value={encode(l.id)} disabled={full(l.id)}>
              {l.name}
              {full(l.id) && fullHint}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

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
        <Field label={t('teams.colLeague')} entity={team.uid} field="league" className="sm:col-span-2" hint={t('teamEdit.leagueHint')}>
          <LeagueSelect value={team.league} onChange={(league) => set({ league })} />
        </Field>
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

function RosterTab({ team }: { team: Team }) {
  const { t } = useI18n()
  const { draft, updatePlayer, updateTeam, addPlayer, defaults } = useProject()
  const { position: positionAbbr } = useLookups()
  const catalog = useCatalog().data
  const navigate = useNavigate()
  const from = useFrom(team.name || t('players.colTeam'))
  const [freeOpen, setFreeOpen] = useState(false)
  const roster = draft.players.filter((p) => p.team === team.uid)
  // hidden players stay listed but are out of the patch: they do not take a roster place
  const active = roster.filter((p) => !p.hidden)
  const freeAgents = draft.players.filter((p) => !p.team)
  const max = catalog?.max_roster ?? 13
  const captain = team.captain ?? active[0]?.uid
  const rosterIssues = useIssues(team.uid, 'players')

  const createPlayer = () => {
    const uid = newUid('jg')
    const used = new Set(roster.map((p) => p.number))
    const number = Array.from({ length: 99 }, (_, i) => i + 1).find((n) => !used.has(n))
    addPlayer({ uid, team: team.uid, first_name: '', last_name: '', generic: true, number, skills: {}, appearance: {}, fields: {} })
    navigate(`/players/${uid}`, from)
  }

  const name = (p: (typeof roster)[number]) => p.display_name || `${p.first_name} ${p.last_name}`.trim() || t('common.unnamed')
  const captainPlayer = active.find((p) => p.uid === captain)
  const roles = effectiveRoles(captain, team.takers ?? {})
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>
            {t('teamEdit.roster')}{' '}
            <span className="font-normal text-muted-foreground">
              ({active.length}/{max})
            </span>
          </CardTitle>
          <CardDescription>{t('teamEdit.rosterDescription')}</CardDescription>
          <CardAction>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setFreeOpen(true)} disabled={active.length >= max}>
                <UserPlus /> {t('teamEdit.addFreeAgent')}
              </Button>
              <Button size="sm" onClick={createPlayer} disabled={active.length >= max}>
                <Plus /> {t('players.new')}
              </Button>
            </div>
          </CardAction>
        </CardHeader>
        <CardContent>
          <FieldIssues issues={rosterIssues} />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('list.colName')}</TableHead>
                <TableHead className="w-24">{t('teamEdit.number')}</TableHead>
                <TableHead className="w-36">{t('players.colPosition')}</TableHead>
                <RoleHeads />
                <TableHead className="w-20" />
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {roster.map((p) => (
                <TableRow key={p.uid}>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <PlayerAvatar player={p} />
                      <Link
                        to={`/players/${p.uid}`}
                        state={from.state}
                        className={cn('font-medium underline-offset-4 hover:underline', p.hidden && 'text-muted-foreground')}
                      >
                        {p.display_name || `${p.first_name} ${p.last_name}`.trim() || t('common.unnamed')}
                      </Link>
                      {p.hidden && <OutOfPatchBadge />}
                    </span>
                  </TableCell>
                  <TableCell>
                    <NumberInput
                      value={p.number}
                      onChange={(v) => updatePlayer(p.uid, { number: v })}
                      min={1}
                      max={99}
                      className="h-8"
                      placeholder={defaults[p.uid]?.number != null ? t('common.inherited', { value: defaults[p.uid].number }) : t('common.default')}
                    />
                  </TableCell>
                  <TableCell>
                    <Select
                      value={p.position === undefined ? AUTO : String(p.position)}
                      onValueChange={(v) => updatePlayer(p.uid, { position: v === AUTO ? undefined : Number(v) })}
                    >
                      <SelectTrigger size="sm" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={AUTO}>
                          {defaults[p.uid]?.position != null
                            ? t('common.inherited', { value: positionAbbr.get(defaults[p.uid].position!) ?? defaults[p.uid].position })
                            : t('street.reset')}
                        </SelectItem>
                        {(catalog?.positions ?? []).map((pos) => (
                          <SelectItem key={pos.code} value={String(pos.code)}>
                            {pos.abbr}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <RoleCells player={p.uid} roles={roles} />
                  <TableCell>
                    <EntityIssues uid={p.uid} />
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      title={t('teamEdit.removeFromTeam')}
                      onClick={() => {
                        updatePlayer(p.uid, { team: null })
                        updateTeam(team.uid, {
                          captain: team.captain === p.uid ? undefined : team.captain,
                          takers: takersWithout(team, p.uid),
                          lineups: lineupsWithout(team, p.uid),
                        })
                      }}
                    >
                      <UserMinus />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
        <Dialog open={freeOpen} onOpenChange={setFreeOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('teamEdit.addFreeAgentTitle')}</DialogTitle>
              <DialogDescription>{t('teamEdit.addFreeAgentDescription')}</DialogDescription>
            </DialogHeader>
            {freeAgents.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('teamEdit.noFreeAgents')}</p>
            ) : (
              <ul className="divide-y">
                {freeAgents.map((p) => (
                  <li key={p.uid} className="flex items-center justify-between py-2">
                    <span>{p.display_name || `${p.first_name} ${p.last_name}`.trim() || t('common.unnamed')}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={roster.length >= max}
                      onClick={() => updatePlayer(p.uid, { team: team.uid })}
                    >
                      {t('common.add')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </DialogContent>
        </Dialog>
      </Card>
      <TakersCard
        entity={team.uid}
        players={active.map((p) => ({ value: p.uid, label: name(p) }))}
        captain={captain}
        takers={team.takers ?? {}}
        fallback={{ label: t('takers.captain', { name: captainPlayer ? name(captainPlayer) : '—' }) }}
        onCaptainChange={(c) => updateTeam(team.uid, { captain: c })}
        onChange={(takers) => updateTeam(team.uid, { takers })}
      />
    </div>
  )
}

function OriginalRosterTab({ team }: { team: Team }) {
  const { t } = useI18n()
  const { updateTeam } = useProject()
  const { position: positionAbbr } = useLookups()
  const players = useOriginalPlayers({ team: team.original_id!, limit: 100 }).data?.items ?? []
  const game = useOriginalTeams().data?.find((o) => o.id === team.original_id)
  const captain = team.captain ?? game?.captain
  const takers = { ...game?.takers, ...team.takers }
  const roles = effectiveRoles(captain, takers)
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>
            {t('teamEdit.roster')} <span className="font-normal text-muted-foreground">({players.length})</span>
          </CardTitle>
          <CardDescription>{t('teamEdit.originalRosterDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('list.colName')}</TableHead>
                <TableHead className="w-24">{t('teamEdit.number')}</TableHead>
                <TableHead className="w-36">{t('players.colPosition')}</TableHead>
                <RoleHeads />
              </TableRow>
            </TableHeader>
            <TableBody>
              {players.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <OriginalPlayerAvatar player={p} />
                      {p.display_name}
                    </span>
                  </TableCell>
                  <TableCell className="tabular-nums">{p.number ?? '—'}</TableCell>
                  <TableCell>{p.position != null ? (positionAbbr.get(p.position) ?? p.position) : '—'}</TableCell>
                  <RoleCells player={p.id} roles={roles} />
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <TakersCard
        entity={team.uid}
        players={players.map((p) => ({ value: p.id, label: p.display_name }))}
        captain={captain}
        takers={takers}
        onCaptainChange={(c) => updateTeam(team.uid, { captain: c })}
        onChange={(takers) => updateTeam(team.uid, { takers })}
      />
    </div>
  )
}

function ProjectLineupTab({ team }: { team: Team }) {
  const { t } = useI18n()
  const { draft, defaults } = useProject()
  const players: LineupPlayer[] = draft.players
    .filter((p) => p.team === team.uid && !p.hidden)
    .map((p) => ({
      ref: p.uid,
      name: p.display_name || `${p.first_name} ${p.last_name}`.trim() || t('common.unnamed'),
      position: p.position ?? defaults[p.uid]?.position,
      avatar: <PlayerAvatar player={p} />,
    }))
  return <LineupEditor team={team} players={players} />
}

function OriginalLineupTab({ team }: { team: Team }) {
  const squad = useOriginalPlayers({ team: team.original_id!, limit: 100 }).data?.items ?? []
  const players: LineupPlayer[] = squad.map((p) => ({
    ref: p.id,
    name: p.display_name,
    position: p.position,
    avatar: <OriginalPlayerAvatar player={p} />,
  }))
  return <LineupEditor team={team} players={players} />
}

export function TeamEditPage() {
  const { t } = useI18n()
  const { uid } = useParams()
  const { draft, removeTeam } = useProject()
  const navigate = useNavigate()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)
  const copy = useCopy()
  const team = draft.teams.find((tm) => tm.uid === uid)
  const back = useBack({ to: '/teams', label: t('nav.teams') })
  const goBack = useGoBack()
  const keepBack = useKeepBack()
  const tabs = useTabParam('data')
  const original = team?.original_id != null

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
        <p className="text-muted-foreground">{t('issue.team_not_found')}</p>
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
          {original && <OriginalBadge edited />}
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
            title={original ? t('teamEdit.restoreOriginalHint') : undefined}
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
        <TabsContent value="data">
          <DataTab team={team} />
        </TabsContent>
        <TabsContent value="crest">
          <CrestTab team={team} />
        </TabsContent>
        <TabsContent value="kits">
          <KitsTab team={team} />
        </TabsContent>
        <TabsContent value="roster">{original ? <OriginalRosterTab team={team} /> : <RosterTab team={team} />}</TabsContent>
        <TabsContent value="lineup">
          {original ? <OriginalLineupTab team={team} /> : <ProjectLineupTab team={team} />}
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
              onClick={() => {
                removeTeam(team.uid)
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
