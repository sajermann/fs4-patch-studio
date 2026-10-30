import { Eye, EyeOff, Lock, LockOpen, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { OriginalTeam, Player, Team } from '@/api/types'
import { EntityIssues, OriginalBadge, OriginalCrest, TeamCrest } from '@/components/common/form'
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
import { defaultLeague, editedOriginals, newLeagues, useLeagueName, useLeagueTeams } from '@/lib/teams'
import { useGamePlayers } from '@/lib/members'
import { linkOf, rosterOf, teamKey, teamPath } from '@/lib/players'
import { newUid, useProject, useSameAsGame } from '@/state/project'
import { useOriginalLeagues, useOriginalTeams } from '@/state/queries'

type Row = { kind: 'project'; team: Team } | { kind: 'original'; team: OriginalTeam }

const NO_LEAGUE = 'none'
const leagueKey = (league: number | string) => (typeof league === 'string' ? `new:${league}` : `orig:${league}`)

export function TeamsPage() {
  const { t } = useI18n()
  const { draft, addTeam, updateTeam } = useProject()
  const games = useGamePlayers()
  // a game team's squad size change: how many joined minus how many left (squads live in the players' links)
  const squadDelta = (teamid: number) => {
    const inGame = (p: Player) => p.original_id != null && !!games.get(p.original_id)?.teams.includes(teamid)
    const joiners = rosterOf(draft, teamid).filter((p) => !p.hidden && !inGame(p)).length
    const leavers = draft.players.filter((p) => inGame(p) && !linkOf(p, teamid)).length
    return joiners - leavers
  }
  // players of a project team: new team = its roster; edited original = its squad size change
  const joined = (team: Team) =>
    team.original_id == null ? rosterOf(draft, teamKey(team)).filter((p) => !p.hidden).length : squadDelta(team.original_id)
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
  // originals only opened (or changed back) list as the game's teams, not the project's
  const sameAsGame = useSameAsGame()
  const mine = draft.teams.filter((tm) => !sameAsGame(tm.uid))
  const edited = editedOriginals({ ...draft, teams: mine })
  const originalById = new Map(originals.map((o) => [o.id, o]))

  // editing an original team: its page loads its data, crest and kits from the game into a project entry (same teamid)
  const edit = (team: OriginalTeam) => navigate(teamPath(team.id), from)

  const create = () => {
    if (firstFreeLeague === null) return
    const uid = newUid()
    addTeam({
      uid,
      name: '',
      leagues: [firstFreeLeague],
      primary_color: [20, 80, 160],
      secondary_color: [245, 245, 245],
      kits: {},
      template: 112298,
    })
    navigate(`/teams/${uid}`, from)
  }

  // a league that keeps its teams out of the game: a hidden new league or a game league the project hides
  const leagueOut = (l: number | string) => (typeof l === 'string' ? hiddenLeagues.has(l) : isLeagueHidden(l))
  // out of the game: hidden by the project (team, no league or every league of it) or by the game itself
  const isHidden = (r: Row) =>
    r.kind === 'project'
      ? !!r.team.hidden ||
        r.team.leagues.every(leagueOut) ||
        (r.team.original_id != null && isTeamHidden(r.team.original_id))
      : isTeamHidden(r.team.id) ||
        (r.team.league !== null && (isLeagueHidden(r.team.league) || gameHiddenLeagues.has(r.team.league)))
  const isLocked = (r: Row) => r.kind === 'original' && r.team.lockable && teamLocked(r.team)

  const rows: Row[] = [
    ...mine.map((team) => ({ kind: 'project' as const, team })),
    ...originals.filter((team) => !edited.has(team.id)).map((team) => ({ kind: 'original' as const, team })),
  ].filter(
    (r) =>
      matches(f.q, r.team.name, r.team.short_name) &&
      (f.origin === ALL ||
        f.origin === r.kind ||
        (f.origin === 'original' && r.kind === 'project' && r.team.original_id != null)) &&
      (f.league === ALL ||
        (r.kind === 'project'
          ? f.league === NO_LEAGUE
            ? r.team.leagues.length === 0
            : r.team.leagues.some((l) => f.league === leagueKey(l))
          : r.team.league !== null && f.league === leagueKey(r.team.league))) &&
      (f.status === ALL ||
        (f.status === 'visible' && !isHidden(r)) ||
        (f.status === 'hidden' && isHidden(r)) ||
        (f.status === 'locked' && isLocked(r))),
  )
  const page = usePage(rows, list.page, list.pageSize)

  const leagueOptions = [
    { value: ALL, label: t('teams.allLeagues') },
    { value: NO_LEAGUE, label: t('teams.noLeague') },
    ...newLeagues(draft).map((l) => ({ value: leagueKey(l.uid), label: l.name || t('league.unnamed'), group: t('teams.newLeagues') })),
    ...originalLeagues.map((l) => ({ value: leagueKey(l.id), label: leagueName(l.id), group: t('teams.originalLeagues') })),
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
                leagueHidden={r.team.leagues.length > 0 && r.team.leagues.every((l) => typeof l === 'string' && hiddenLeagues.has(l))}
                original={r.team.original_id != null ? originalById.get(r.team.original_id) : undefined}
                originalHidden={r.team.original_id != null && isTeamHidden(r.team.original_id)}
                players={joined(r.team)}
                leagueName={r.team.leagues.length ? r.team.leagues.map(leagueName).join(', ') : leagueName(null)}
                onOpen={() => navigate(teamPath(teamKey(r.team)), from)}
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
                onClick={() => edit(r.team)}
              >
                <TableCell>
                  <OriginalCrest team={r.team} />
                </TableCell>
                <TableCell data-grow>
                  <span className="mr-2 text-foreground">{r.team.name}</span>
                  <OriginalBadge team={r.team.id} />
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
                <TableCell className="tabular-nums">{r.team.player_count + squadDelta(r.team.id)}</TableCell>
                <TableCell className="tabular-nums">{r.team.id}</TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <span className="flex items-center gap-1">
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
  players: number // new team: its roster; original: how many join it without taking someone's place
  leagueName: string
  onOpen: () => void
  onToggleHidden: () => void
}) {
  const { t } = useI18n()
  const hidden = original ? originalHidden : !!team.hidden
  return (
    <TableRow className="cursor-pointer" onClick={onOpen}>
      <TableCell>
        <TeamCrest team={team} />
      </TableCell>
      <TableCell data-grow className={hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
        <span className="mr-2">{team.name || <span className="text-muted-foreground">{t('common.unnamed')}</span>}</span>
        {team.original_id != null && <OriginalBadge entry={team.uid} team={team.original_id} />}
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
      <TableCell className="tabular-nums">{original ? original.player_count + players : players}</TableCell>
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
