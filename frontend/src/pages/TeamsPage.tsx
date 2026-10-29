import { Eye, EyeOff, Loader2, Lock, LockOpen, Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api, imageUrl } from '@/api/client'
import type { OriginalTeam, Team } from '@/api/types'
import { EntityIssues, OriginalBadge, OriginalCrest, Swatch } from '@/components/common/form'
import { GameHiddenBadge, HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import {
  ALL,
  FilterBar,
  FilterSelect,
  LIST_PAGE,
  matches,
  Pager,
  ScrollTable,
  SearchInput,
  useListParams,
  usePage,
} from '@/components/common/list'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { useOriginalChanges } from '@/lib/originals'
import { defaultLeague, editedOriginals, useLeagueName, useLeagueTeams } from '@/lib/teams'
import { newUid, useProject } from '@/state/project'
import { useOriginalLeagues, useOriginalTeams } from '@/state/queries'

type Row = { kind: 'project'; team: Team } | { kind: 'original'; team: OriginalTeam }

const leagueKey = (league: number | string | null) => (typeof league === 'string' ? `new:${league}` : `orig:${league}`)

export function TeamsPage() {
  const { t } = useI18n()
  const { draft, addTeam, updateTeam } = useProject()
  const originalLeagues = useOriginalLeagues().data ?? []
  const originals = useOriginalTeams().data ?? []
  const leagueName = useLeagueName()
  const navigate = useNavigate()
  const from = useFrom(t('nav.teams'))
  const { isLeagueHidden, isTeamHidden, toggleTeam, teamLocked, setTeamLocked } = useOriginalChanges()
  const hiddenLeagues = new Set(draft.leagues.filter((l) => l.hidden).map((l) => l.uid))
  const gameHiddenLeagues = new Set(originalLeagues.filter((l) => l.hidden).map((l) => l.id))
  const leagueTeams = useLeagueTeams()
  const firstFreeLeague = defaultLeague(draft, originalLeagues, leagueTeams.isFull)
  const list = useListParams(['q', 'origin', 'league', 'status'] as const)
  const f = list.values
  const edited = editedOriginals(draft)
  const originalById = new Map(originals.map((o) => [o.id, o]))
  const [opening, setOpening] = useState<number>()

  // editing an original team: its data, crest and kits come from the game into a project entry (same teamid)
  const edit = async (team: OriginalTeam) => {
    if (opening !== undefined) return
    setOpening(team.id)
    try {
      const entry = await api.editOriginalTeam(team.id, newUid('tm'))
      addTeam(entry)
      navigate(`/teams/${entry.uid}`, from)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('teams.editOriginalFailed'))
    } finally {
      setOpening(undefined)
    }
  }

  const create = () => {
    if (firstFreeLeague === null) return
    const uid = newUid('tm')
    addTeam({
      uid,
      name: '',
      league: firstFreeLeague,
      primary_color: [20, 80, 160],
      secondary_color: [245, 245, 245],
      kits: {},
      template: 112298,
    })
    navigate(`/teams/${uid}`, from)
  }

  // out of the game: hidden by the project (team or its league) or by the game itself
  const isHidden = (r: Row) =>
    r.kind === 'project'
      ? !!r.team.hidden ||
        (r.team.original_id != null && isTeamHidden(r.team.original_id)) ||
        (typeof r.team.league === 'string' && hiddenLeagues.has(r.team.league)) ||
        (typeof r.team.league === 'number' && isLeagueHidden(r.team.league))
      : isTeamHidden(r.team.id) ||
        (r.team.league !== null && (isLeagueHidden(r.team.league) || gameHiddenLeagues.has(r.team.league)))
  const isLocked = (r: Row) => r.kind === 'original' && r.team.lockable && teamLocked(r.team)

  const rows: Row[] = [
    ...draft.teams.map((team) => ({ kind: 'project' as const, team })),
    ...originals.filter((team) => !edited.has(team.id)).map((team) => ({ kind: 'original' as const, team })),
  ].filter(
    (r) =>
      matches(f.q, r.team.name, r.team.short_name) &&
      (f.origin === ALL ||
        f.origin === r.kind ||
        (f.origin === 'original' && r.kind === 'project' && r.team.original_id != null)) &&
      (f.league === ALL || f.league === leagueKey(r.team.league)) &&
      (f.status === ALL ||
        (f.status === 'visible' && !isHidden(r)) ||
        (f.status === 'hidden' && isHidden(r)) ||
        (f.status === 'locked' && isLocked(r))),
  )
  const page = usePage(rows, list.page, list.pageSize)

  const leagueOptions = [
    { value: ALL, label: t('teams.allLeagues') },
    ...draft.leagues.map((l) => ({ value: leagueKey(l.uid), label: l.name || t('league.unnamed'), group: t('teams.newLeagues') })),
    ...originalLeagues.map((l) => ({ value: leagueKey(l.id), label: l.name, group: t('teams.originalLeagues') })),
  ]

  return (
    <div className={LIST_PAGE}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.teams')}</h1>
          <p className="text-sm text-muted-foreground">{t('teams.description')}</p>
        </div>
        <Button
          onClick={create}
          disabled={firstFreeLeague === null}
          title={firstFreeLeague === null ? t('teams.allLeaguesFull', { max: leagueTeams.max }) : undefined}
        >
          <Plus /> {t('teams.new')}
        </Button>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('teams.search')} />
        <FilterSelect
          value={f.origin}
          onChange={(v) => list.set('origin', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.originAll') },
            { value: 'project', label: t('list.originProject') },
            { value: 'original', label: t('list.originOriginal') },
          ]}
        />
        <FilterSelect value={f.league} onChange={(v) => list.set('league', v)} options={leagueOptions} className="w-56" />
        <FilterSelect
          value={f.status}
          onChange={(v) => list.set('status', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.statusAll') },
            { value: 'visible', label: t('list.statusInGame') },
            { value: 'hidden', label: t('teams.statusHidden') },
            { value: 'locked', label: t('teams.statusLocked') },
          ]}
        />
      </FilterBar>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12" />
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('teams.colLeague')}</TableHead>
            <TableHead>{t('nav.players')}</TableHead>
            <TableHead>{t('list.colId')}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                {list.active ? t('teams.noneFiltered') : t('teams.noneYet')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((r) =>
            r.kind === 'project' ? (
              <ProjectTeamRow
                key={r.team.uid}
                team={r.team}
                leagueHidden={typeof r.team.league === 'string' && hiddenLeagues.has(r.team.league)}
                original={r.team.original_id != null ? originalById.get(r.team.original_id) : undefined}
                originalHidden={r.team.original_id != null && isTeamHidden(r.team.original_id)}
                players={draft.players.filter((p) => p.team === r.team.uid).length}
                leagueName={leagueName(r.team.league)}
                onOpen={() => navigate(`/teams/${r.team.uid}`, from)}
                onToggleHidden={() =>
                  r.team.original_id != null
                    ? toggleTeam(r.team.original_id)
                    : updateTeam(r.team.uid, { hidden: !r.team.hidden })
                }
              />
            ) : (
              <TableRow
                key={r.team.id}
                className="cursor-pointer text-muted-foreground"
                title={t('teams.editOriginalHint')}
                onClick={() => void edit(r.team)}
              >
                <TableCell>
                  <OriginalCrest team={r.team} />
                </TableCell>
                <TableCell data-grow>
                  <span className="mr-2 text-foreground">{r.team.name}</span>
                  <OriginalBadge />
                  {r.team.lockable && (
                    <Badge variant="outline" className="ml-1 font-normal">
                      {teamLocked(r.team) ? t('teams.badgeLocked') : t('teams.badgeUnlocked')}
                    </Badge>
                  )}
                  {r.team.league !== null && gameHiddenLeagues.has(r.team.league) && <GameHiddenBadge team />}
                  {(isTeamHidden(r.team.id) || (r.team.league !== null && isLeagueHidden(r.team.league))) && (
                    <Badge variant="outline" className="ml-1 font-normal">
                      {isTeamHidden(r.team.id) ? t('teams.hiddenByProject') : t('teams.leagueHidden')}
                    </Badge>
                  )}
                </TableCell>
                <TableCell>{r.team.league !== null ? leagueName(r.team.league) : '—'}</TableCell>
                <TableCell className="tabular-nums">{r.team.player_count}</TableCell>
                <TableCell className="tabular-nums">{r.team.id}</TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <span className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      title={t('teams.editOriginalHint')}
                      disabled={opening !== undefined}
                      onClick={() => void edit(r.team)}
                    >
                      {opening === r.team.id ? <Loader2 className="animate-spin" /> : <Pencil />}
                    </Button>
                    <OriginalTeamAction
                    team={r.team}
                    gameHidden={r.team.league !== null && gameHiddenLeagues.has(r.team.league)}
                    locked={teamLocked(r.team)}
                    hidden={isTeamHidden(r.team.id)}
                    onLock={() => setTeamLocked(r.team, !teamLocked(r.team))}
                      onToggleHidden={() => toggleTeam(r.team.id)}
                    />
                  </span>
                </TableCell>
              </TableRow>
            ),
          )}
        </TableBody>
      </ScrollTable>
      <Pager page={page.page} pages={page.pages} total={page.total} pageSize={list.pageSize} onPage={list.setPage} />
    </div>
  )
}

function ProjectTeamRow({
  team,
  leagueHidden,
  original,
  originalHidden,
  players,
  leagueName,
  onOpen,
  onToggleHidden,
}: {
  team: Team
  leagueHidden: boolean
  original?: OriginalTeam // the game's team this entry edits
  originalHidden: boolean
  players: number
  leagueName: string
  onOpen: () => void
  onToggleHidden: () => void
}) {
  const { t } = useI18n()
  const hidden = original ? originalHidden : !!team.hidden
  return (
    <TableRow className="cursor-pointer" onClick={onOpen}>
      <TableCell>
        {team.crest ? (
          <img src={imageUrl(team.crest)} alt="" className="size-8 object-contain" />
        ) : (
          <span className="flex gap-0.5">
            <Swatch rgb={team.primary_color} />
            <Swatch rgb={team.secondary_color} />
          </span>
        )}
      </TableCell>
      <TableCell data-grow className={hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
        <span className="mr-2">{team.name || <span className="text-muted-foreground">{t('common.unnamed')}</span>}</span>
        {team.original_id != null && <OriginalBadge edited />}
        {original && originalHidden ? (
          <Badge variant="outline" className="ml-1 font-normal">
            {t('teams.hiddenByProject')}
          </Badge>
        ) : team.hidden ? (
          <OutOfPatchBadge />
        ) : (
          leagueHidden && <OutOfPatchBadge label={t('teams.leagueOutOfPatch')} />
        )}
      </TableCell>
      <TableCell>{leagueName}</TableCell>
      <TableCell className="tabular-nums">{original ? original.player_count : players}</TableCell>
      <TableCell className="tabular-nums text-muted-foreground">
        {team.original_id ?? team.team_id ?? t('common.auto')}
      </TableCell>
      <TableCell>
        <span className="flex items-center gap-1">
          <EntityIssues uid={team.uid} />
          <HideButton
            hidden={hidden}
            onToggle={onToggleHidden}
            hideHint={original ? t('teams.originalHideHint') : t('teams.hideHint')}
            showHint={original ? t('teams.originalShowHint') : t('teams.showHint')}
          />
        </span>
      </TableCell>
    </TableRow>
  )
}

/** Lock/unlock for the special teams the game locks; hide/show for the others (not for leagues the game hides). */
function OriginalTeamAction({
  team,
  gameHidden,
  locked,
  hidden,
  onLock,
  onToggleHidden,
}: {
  team: OriginalTeam
  gameHidden: boolean
  locked: boolean
  hidden: boolean
  onLock: () => void
  onToggleHidden: () => void
}) {
  const { t } = useI18n()
  if (team.lockable)
    return (
      <Button variant="ghost" size="sm" onClick={onLock}>
        {locked ? <LockOpen /> : <Lock />} {locked ? t('list.unlock') : t('list.lock')}
      </Button>
    )
  if (team.league === null || gameHidden) return null
  return (
    <Button
      variant="ghost"
      size="sm"
      title={hidden ? t('teams.originalShowHint') : t('teams.originalHideHint')}
      onClick={onToggleHidden}
    >
      {hidden ? <Eye /> : <EyeOff />} {hidden ? t('list.show') : t('list.hide')}
    </Button>
  )
}
