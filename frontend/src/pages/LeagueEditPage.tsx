import { ArrowRightLeft, Copy, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, imageUrl } from '@/api/client'
import type { Team } from '@/api/types'
import { EntityIssues, Field, NumberInput, OriginalBadge, OriginalCrest, Swatch } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { BackButton, useBack, useFrom, useGoBack, useKeepBack } from '@/lib/back'
import { useI18n } from '@/i18n'
import { useCopy } from '@/lib/copy'
import { useProject } from '@/state/project'
import { useLookups, useOriginalTeams } from '@/state/queries'

/** Moves one of the project's teams into this league (only changes the team's league field). */
function MoveTeamDialog({ league, open, onOpenChange }: { league: number | string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const { t } = useI18n()
  const { draft, updateTeam } = useProject()
  const [team, setTeam] = useState<string>()
  const candidates = draft.teams.filter((tm) => tm.league !== league)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('leagueEdit.moveTeam')}</DialogTitle>
          <DialogDescription>{t('leagueEdit.moveTeamDescription')}</DialogDescription>
        </DialogHeader>
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('leagueEdit.noOtherTeams')}</p>
        ) : (
          <Select value={team} onValueChange={setTeam}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('leagueEdit.pickTeam')} />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((tm) => (
                <SelectItem key={tm.uid} value={tm.uid}>
                  {tm.name || t('common.unnamed')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <DialogFooter>
          <Button
            disabled={!team}
            onClick={() => {
              if (team) updateTeam(team, { league })
              setTeam(undefined)
              onOpenChange(false)
            }}
          >
            {t('leagueEdit.moveHere')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ProjectTeamsTable({ teams, leagueName }: { teams: Team[]; leagueName: string }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const from = useFrom(leagueName)
  if (!teams.length) return <p className="text-sm text-muted-foreground">{t('leagueEdit.noTeams')}</p>
  return (
    <Table>
      <TableBody>
        {teams.map((tm) => (
          <TableRow key={tm.uid} className="cursor-pointer" onClick={() => navigate(`/teams/${tm.uid}`, from)}>
            <TableCell className="w-8">
              <Swatch rgb={tm.primary_color} />
            </TableCell>
            <TableCell className="font-medium">{tm.name || t('common.unnamed')}</TableCell>
            <TableCell className="w-24">
              <EntityIssues uid={tm.uid} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function LeagueEditPage() {
  const { t } = useI18n()
  const { key = '' } = useParams()
  const { draft, updateLeague, removeLeague } = useProject()
  const lookups = useLookups()
  const originalTeams = useOriginalTeams().data ?? []
  const navigate = useNavigate()
  const [moveOpen, setMoveOpen] = useState(false)
  const copy = useCopy()

  const league = draft.leagues.find((l) => l.uid === key)
  const original = !league && /^\d+$/.test(key) ? lookups.originalLeague.get(Number(key)) : undefined
  const leagueRef: number | string | undefined = league?.uid ?? original?.id
  const originalLeagueOf = new Map(originalTeams.map((tm) => [tm.id, tm.league]))
  const projectTeams = draft.teams.filter(
    (tm) => tm.league === leagueRef && (tm.original_id == null || originalLeagueOf.get(tm.original_id) !== leagueRef),
  )
  const movedAway = new Set(
    draft.teams.filter((tm) => tm.original_id != null && tm.league !== originalLeagueOf.get(tm.original_id)).map((tm) => tm.original_id!),
  )

  const back = useBack({ to: '/leagues', label: t('nav.leagues') })
  const goBack = useGoBack()
  const keepBack = useKeepBack()

  if (!league && !original) {
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        <p className="text-muted-foreground">{t('issue.league_not_found')}</p>
      </div>
    )
  }

  const teamsCard = (
    <Card>
      <CardHeader>
        <CardTitle>{t('leagueEdit.projectTeams')}</CardTitle>
        <CardDescription>{t('leagueEdit.projectTeamsDescription')}</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" onClick={() => setMoveOpen(true)}>
            <ArrowRightLeft /> {t('leagueEdit.moveTeam')}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <ProjectTeamsTable teams={projectTeams} leagueName={league?.name || original?.name || t('teams.colLeague')} />
      </CardContent>
      {leagueRef !== undefined && <MoveTeamDialog league={leagueRef} open={moveOpen} onOpenChange={setMoveOpen} />}
    </Card>
  )

  if (original) {
    const teams = originalTeams.filter((tm) => tm.league === original.id && !movedAway.has(tm.id))
    return (
      <div className="max-w-3xl space-y-4">
        <BackButton back={back} />
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">{original.name}</h1>
          <OriginalBadge />
        </div>
        <p className="text-sm text-muted-foreground">{t('leagueEdit.originalDescription', { id: original.id })}</p>
        {teamsCard}
        <Card>
          <CardHeader>
            <CardTitle>{t('leagueEdit.originalTeams', { count: teams.length })}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            {teams.map((tm) => (
              <span key={tm.id} className="flex items-center gap-2">
                <OriginalCrest team={tm} className="size-6" /> {tm.name}
              </span>
            ))}
          </CardContent>
        </Card>
      </div>
    )
  }

  const l = league!
  const canDelete = projectTeams.length === 0

  return (
    <div className="max-w-3xl space-y-4">
      <BackButton back={back} />
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{l.name || t('leagues.new')}</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!copy.canCopyLeague}
            title={
              copy.canCopyLeague ? t('leagueEdit.copyHint') : t('leagueEdit.copyMax', { max: copy.maxLeagues })
            }
            onClick={() => {
              const uid = copy.copyLeague(l.uid)
              if (uid) navigate(`/leagues/${uid}`, keepBack)
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
        </div>
      </div>
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
            hint={t('leagueEdit.logoHint')}
          >
            <LeagueImageInput
              path={l.image}
              preview="size-16"
              onUpload={async (f) => updateLeague(l.uid, { image: (await api.uploadImage(f)).path })}
              onRemove={() => updateLeague(l.uid, { image: undefined })}
            />
          </Field>
          <Field
            label={t('leagueEdit.wideImage')}
            entity={l.uid}
            field="wide_image"
            hint={t('leagueEdit.wideImageHint')}
          >
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
        </CardContent>
      </Card>
      {teamsCard}
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
  onRemove: () => void
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
      {path && (
        <Button variant="ghost" size="sm" onClick={onRemove}>
          {t('common.remove')}
        </Button>
      )}
    </div>
  )
}
