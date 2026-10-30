import { Copy, LoaderCircle, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, imageUrl } from '@/api/client'
import type { League, LeagueKey, OriginalTeam, Team, TeamKey } from '@/api/types'
import { EntityIssues, Field, NumberInput, OriginalBadge, OriginalCrest, TeamCrest } from '@/components/common/form'
import { OutOfPatchBadge } from '@/components/common/HideButton'
import { matches } from '@/components/common/list'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { BackButton, useBack, useFrom, useGoBack, useKeepBack } from '@/lib/back'
import { useI18n } from '@/i18n'
import { useCopy } from '@/lib/copy'
import { useEntryOfPath, useTeamLeagues } from '@/lib/members'
import { useOriginalChanges } from '@/lib/originals'
import { keyOfPath, leagueKey, leaguePath, teamKey, teamPath } from '@/lib/players'
import { editedOriginals, useLeagueName, useLeagueTeams } from '@/lib/teams'
import { useProject, useWasEdited } from '@/state/project'
import { useOriginalLeagues, useOriginalTeams } from '@/state/queries'

/** A team of the league list: a project entry (new team or edited original) or one of the game's as it is. */
interface LeagueTeam {
  key: TeamKey
  name: string
  icon: ReactNode
  team?: Team
  game?: OriginalTeam
}

/** Teams in a league (new league uid or original leagueid): the project's and the game's ones the project does not
 * move away, all shown the same way. */
function useTeamsIn(league: LeagueKey): LeagueTeam[] {
  const { t } = useI18n()
  const { draft } = useProject()
  const originals = useOriginalTeams().data ?? []
  const edited = editedOriginals(draft)
  return [
    ...draft.teams
      .filter((tm) => tm.leagues.includes(league))
      .map((tm) => ({ key: teamKey(tm), name: tm.name || t('common.unnamed'), icon: <TeamCrest team={tm} />, team: tm })),
    ...originals
      .filter((o) => o.league === league && !edited.has(o.id))
      .map((o) => ({ key: o.id, name: o.name, icon: <OriginalCrest team={o} />, game: o })),
  ].sort((a, b) => a.name.localeCompare(b.name))
}

/** Dialog: every team not in the league (project and game), with a search; the team joins this league and keeps
 * its other ones. */
function AddTeamDialog({ league, open, onOpenChange }: { league: LeagueKey; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const originals = useOriginalTeams().data ?? []
  const leagueName = useLeagueName()
  const leagueTeams = useLeagueTeams()
  const { join } = useTeamLeagues()
  const [q, setQ] = useState('')
  const edited = editedOriginals(draft)
  const leaguesOf = (leagues: LeagueKey[]) => (leagues.length ? leagues.map(leagueName).join(', ') : leagueName(null))
  // new teams, then the game's (edited ones by their entry), each group by name
  const toItems = (list: { key: TeamKey; name: string; icon: ReactNode; leagues: LeagueKey[] }[]): PickerItem<TeamKey>[] =>
    list
      .filter((c) => matches(q, c.name))
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((c) => ({ key: c.key, icon: c.icon, title: c.name, subtitle: leaguesOf(c.leagues) }))
  const newTeams = toItems(
    draft.teams
      .filter((tm) => tm.original_id == null && !tm.leagues.includes(league))
      .map((tm) => ({ key: tm.uid, name: tm.name || t('common.unnamed'), icon: <TeamCrest team={tm} />, leagues: tm.leagues })),
  )
  const gameTeams = toItems([
    ...draft.teams
      .filter((tm) => tm.original_id != null && !tm.leagues.includes(league))
      .map((tm) => ({ key: teamKey(tm), name: tm.name, icon: <TeamCrest team={tm} />, leagues: tm.leagues })),
    ...originals
      .filter((o) => o.league !== league && !edited.has(o.id))
      .map((o) => ({ key: o.id, name: o.name, icon: <OriginalCrest team={o} />, leagues: o.league === null ? [] : [o.league] })),
  ])
  const full = leagueTeams.isFull(league)
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('leagueEdit.addTeamTitle')}
      description={t('leagueEdit.addTeamDescription')}
      placeholder={t('teams.search')}
      query={q}
      onQuery={setQ}
      groups={[
        { label: t('players.newTeams'), items: newTeams },
        { label: t('players.originalTeams'), items: gameTeams },
      ]}
      notice={full ? t('leagueEdit.full', { max: leagueTeams.max }) : undefined}
      empty={t('leagueEdit.noTeamsFound')}
      disabled={full}
      onPick={(key) => join(key, league)}
    />
  )
}

/** The league's teams: crest, name (link to the team), badges and a button that takes the team out of the league
 * (it is left without a league, out of the patch, until it joins another one). readOnly: a league the game hides. */
function LeagueTeamsCard({ league, leagueName, readOnly }: { league: LeagueKey; leagueName: string; readOnly?: boolean }) {
  const { t } = useI18n()
  const teams = useTeamsIn(league)
  const leagueTeams = useLeagueTeams()
  const { isTeamHidden } = useOriginalChanges()
  const { leave } = useTeamLeagues()
  const from = useFrom(leagueName)
  const [addOpen, setAddOpen] = useState(false)
  const [removing, setRemoving] = useState<LeagueTeam>()
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {t('leagueEdit.teams')}{' '}
          <span className="font-normal text-muted-foreground">
            ({leagueTeams.count(league)}/{leagueTeams.max})
          </span>
        </CardTitle>
        <CardDescription>{t('leagueEdit.teamsDescription')}</CardDescription>
        {!readOnly && (
          <CardAction>
            <Button
              variant="outline"
              size="sm"
              title={leagueTeams.isFull(league) ? t('leagueEdit.full', { max: leagueTeams.max }) : undefined}
              onClick={() => setAddOpen(true)}
            >
              <Plus /> {t('leagueEdit.addTeam')}
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {teams.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('leagueEdit.noTeams')}</p>
        ) : (
          <Table>
            <TableBody>
              {teams.map((r) => {
                const gameId = r.team?.original_id ?? r.game?.id
                const hidden = !!r.team?.hidden || (gameId != null && isTeamHidden(gameId))
                return (
                  <TableRow key={String(r.key)}>
                    <TableCell className="w-12">{r.icon}</TableCell>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <Link
                          to={teamPath(r.key)}
                          state={from.state}
                          className={hidden ? 'font-medium text-muted-foreground underline-offset-4 hover:underline' : 'font-medium underline-offset-4 hover:underline'}
                        >
                          {r.name}
                        </Link>
                        {gameId != null && <OriginalBadge entry={r.team?.uid} team={gameId} />}
                        {r.team?.hidden && <OutOfPatchBadge />}
                        {!r.team?.hidden && gameId != null && isTeamHidden(gameId) && (
                          <Badge variant="outline" className="font-normal">
                            {t('teams.hiddenByProject')}
                          </Badge>
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="w-20">{r.team && <EntityIssues uid={r.team.uid} />}</TableCell>
                    {!readOnly && (
                      <TableCell className="w-12">
                        <Button variant="ghost" size="icon" title={t('leagueEdit.removeTeam')} onClick={() => setRemoving(r)}>
                          <X />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {!readOnly && <AddTeamDialog league={league} open={addOpen} onOpenChange={setAddOpen} />}
      <AlertDialog open={!!removing} onOpenChange={(o) => !o && setRemoving(undefined)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('leagueEdit.removeTeamTitle', { team: removing?.name ?? '' })}</AlertDialogTitle>
            <AlertDialogDescription>{t('leagueEdit.removeTeamDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => removing && void leave(removing.key, league)}>
              {t('leagueEdit.removeTeam')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

export function LeagueEditPage() {
  const { t } = useI18n()
  const { key: param } = useParams()
  const { draft, setDraft, updateLeague, removeLeague } = useProject()
  const gameTeams = useOriginalTeams().data ?? []
  const gameLeagues = useOriginalLeagues().data
  const navigate = useNavigate()
  const copy = useCopy()
  const key = keyOfPath(param)
  const game = typeof key === 'number' ? gameLeagues?.find((l) => l.id === key) : undefined
  // a league the game's selector hides is shown, not edited (the backend refuses to load it)
  const { entry: league, loading } = useEntryOfPath<League>('league', param, !!gameLeagues && !game?.hidden)
  const edited = useWasEdited(league?.uid, null, league?.original_id)
  const [restoreOpen, setRestoreOpen] = useState(false)
  const back = useBack({ to: '/leagues', label: t('nav.leagues') })
  const goBack = useGoBack()
  const keepBack = useKeepBack()

  if (!league) {
    if (game?.hidden) {
      return (
        <div className="max-w-3xl space-y-4">
          <BackButton back={back} />
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold">{game.name}</h1>
            <OriginalBadge />
          </div>
          <p className="text-sm text-muted-foreground">{t('leagueEdit.notEditable', { id: game.id })}</p>
          <LeagueTeamsCard league={game.id} leagueName={game.name} readOnly />
        </div>
      )
    }
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        {loading || !gameLeagues ? (
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <p className="text-muted-foreground">{t('issue.league_not_found')}</p>
        )}
      </div>
    )
  }

  const l = league
  const original = l.original_id != null
  const canDelete = !draft.teams.some((tm) => tm.leagues.includes(l.uid))
  // restoring an original league also gives it back its teams: who joined leaves it, who left comes back (each team
  // keeps its other leagues)
  const restore = () => {
    const id = l.original_id!
    const ownTeams = new Set(gameTeams.filter((o) => o.league === id).map((o) => o.id))
    setDraft((p) => ({
      ...p,
      teams: p.teams.map((tm) => {
        const own = tm.original_id != null && ownTeams.has(tm.original_id)
        if (own === tm.leagues.includes(id)) return tm
        return { ...tm, leagues: own ? [...tm.leagues, id] : tm.leagues.filter((x) => x !== id) }
      }),
    }))
    removeLeague(l.uid)
    goBack(back)
  }

  return (
    <div className="max-w-3xl space-y-4">
      <BackButton back={back} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">{l.name || t('leagues.new')}</h1>
          {original && <OriginalBadge entry={l.uid} league={l.original_id} />}
        </div>
        <div className="flex gap-2">
          {original ? (
            <Button
              variant="outline"
              size="sm"
              disabled={!edited}
              title={edited ? t('leagueEdit.restoreOriginalHint') : t('common.unchangedHint')}
              onClick={() => setRestoreOpen(true)}
            >
              <RotateCcw /> {t('teamEdit.restoreOriginal')}
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={!copy.canCopyLeague}
                title={copy.canCopyLeague ? t('leagueEdit.copyHint') : t('leagueEdit.copyMax', { max: copy.maxLeagues })}
                onClick={() => {
                  const uid = copy.copyLeague(l.uid)
                  if (uid) navigate(leaguePath(uid), keepBack)
                }}
              >
                <Copy /> {t('common.copy')}
              </Button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!canDelete}
                      onClick={() => {
                        removeLeague(l.uid)
                        goBack(back)
                      }}
                    >
                      <Trash2 /> {t('leagueEdit.delete')}
                    </Button>
                  </span>
                </TooltipTrigger>
                {!canDelete && <TooltipContent>{t('leagueEdit.cannotDelete')}</TooltipContent>}
              </Tooltip>
            </>
          )}
        </div>
      </div>
      {original && <p className="text-sm text-muted-foreground">{t('leagueEdit.originalDescription', { id: l.original_id! })}</p>}
      <Card>
        <CardContent className="grid gap-4 pt-6 sm:grid-cols-2">
          <Field label={t('list.colName')} entity={l.uid} field="name">
            <Input value={l.name} onChange={(e) => updateLeague(l.uid, { name: e.target.value })} autoFocus={!l.name} />
          </Field>
          <Field label={t('leagueEdit.shortName')} entity={l.uid} field="short_name" hint={t('leagueEdit.shortNameHint')}>
            <Input value={l.short_name ?? ''} onChange={(e) => updateLeague(l.uid, { short_name: e.target.value || undefined })} />
          </Field>
          <Field label={t('leagueEdit.sortOrder')} entity={l.uid} field="sort_order" hint={t('leagueEdit.sortOrderHint')}>
            <NumberInput value={l.sort_order} onChange={(v) => updateLeague(l.uid, { sort_order: v ?? 0 })} />
          </Field>
          <Field
            label={t('leagueEdit.logo')}
            entity={l.uid}
            field="image"
            hint={original ? `${t('leagueEdit.logoHint')} ${t('leagueEdit.originalLogoHint')}` : t('leagueEdit.logoHint')}
          >
            <LeagueImageInput
              path={l.image}
              preview="size-16"
              onUpload={async (f) => updateLeague(l.uid, { image: (await api.uploadImage(f)).path })}
              onRemove={original ? undefined : () => updateLeague(l.uid, { image: undefined })}
            />
          </Field>
          <Field label={t('leagueEdit.wideImage')} entity={l.uid} field="wide_image" hint={t('leagueEdit.wideImageHint')}>
            <LeagueImageInput
              path={l.wide_image}
              preview={`h-12 aspect-[250/116] ${l.wide_image_fit === 'cover' ? 'object-cover' : 'object-contain'}`}
              fallback={l.image}
              onUpload={async (f) => updateLeague(l.uid, { wide_image: (await api.uploadImage(f)).path })}
              onRemove={() => updateLeague(l.uid, { wide_image: undefined })}
            />
          </Field>
          <Field label={t('leagueEdit.wideImageFit')} entity={l.uid} field="wide_image_fit">
            <Select
              value={l.wide_image_fit ?? 'contain'}
              onValueChange={(v) => updateLeague(l.uid, { wide_image_fit: v as 'contain' | 'cover' })}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="contain">{t('leagueEdit.fitContain')}</SelectItem>
                <SelectItem value="cover">{t('leagueEdit.fitCover')}</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <div className="sm:col-span-2">
            <EntityIssues uid={l.uid} />
          </div>
        </CardContent>
      </Card>
      <LeagueTeamsCard league={leagueKey(l)} leagueName={l.name || t('teams.colLeague')} />
      <AlertDialog open={restoreOpen} onOpenChange={setRestoreOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('teamEdit.restoreOriginalTitle', { name: l.name })}</AlertDialogTitle>
            <AlertDialogDescription>{t('leagueEdit.restoreOriginalDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={restore}>
              {t('teamEdit.restoreOriginal')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function LeagueImageInput({
  path,
  preview,
  fallback,
  onUpload,
  onRemove,
}: {
  path?: string
  preview: string
  fallback?: string
  onUpload: (file: File) => Promise<void>
  onRemove?: () => void
}) {
  const { t } = useI18n()
  const shown = path ?? fallback
  return (
    <div className="flex items-center gap-3">
      {shown && (
        <img src={imageUrl(shown)} alt="" className={`${preview} rounded border bg-muted ${path ? '' : 'opacity-50'}`} />
      )}
      <Input
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={async (e) => {
          const f = e.target.files?.[0]
          e.target.value = ''
          if (!f) return
          try {
            await onUpload(f)
          } catch (err) {
            toast.error(err instanceof ApiError ? err.message : t('image.uploadFailed'))
          }
        }}
      />
      {path && onRemove && (
        <Button variant="ghost" size="sm" onClick={onRemove}>
          {t('common.remove')}
        </Button>
      )}
    </div>
  )
}
