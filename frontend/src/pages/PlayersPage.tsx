import { DateCells, DateHeads } from '@/components/common/dates'
import { Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { OriginalPlayer, Player, TeamKey } from '@/api/types'
import { EntityIssues, OriginalBadge } from '@/components/common/form'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { BulkActions, RowCheckbox, SelectAllCheckbox, SelectAllDialog, ShareImportButton, useListSelection } from '@/components/common/share'
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
  YesNoCell,
} from '@/components/common/list'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { useTeamName } from '@/lib/members'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { linkOf, playerPath, playerRef } from '@/lib/players'
import { newUid, useProject, useSameAsGame } from '@/state/project'
import { useLookups, useOriginalPlayers, useOriginalTeams } from '@/state/queries'

/** What head a project player wears: a real face of a pack, the game's scanned one (an original kept as is) or the
 * generic one. */
const faceKind = (p: Player) =>
  p.generic ? 'players.faceGeneric' : p.face ? 'players.faceReal' : p.original_id != null ? 'players.faceGame' : 'players.faceGeneric'

type Row = { kind: 'project'; player: Player } | { kind: 'original'; player: OriginalPlayer }

const FREE = 'free'
const ALL_ORIGINALS = { limit: 5000 } // the whole list (2,213 players) once: filtered here with the project's

export function PlayersPage() {
  const { t } = useI18n()
  const { draft, addPlayer, updatePlayer, removePlayer, defaults } = useProject()
  const { position, originalTeam } = useLookups()
  const originalTeams = useOriginalTeams().data ?? []
  const originalsQuery = useOriginalPlayers(ALL_ORIGINALS)
  const originals = originalsQuery.data?.items
  const navigate = useNavigate()
  const from = useFrom(t('nav.players'))
  const list = useListParams(['q', 'origin', 'team', 'status'] as const)
  const f = list.values
  const teamName = useTeamName()

  const create = () => {
    const uid = newUid()
    addPlayer({
      uid,
      teams: f.team.startsWith('new:') ? [{ team: f.team.slice(4) }] : [],
      first_name: '',
      last_name: '',
      generic: true,
      skills: {},
      appearance: {},
      fields: {},
    })
    navigate(`/players/${uid}`, from)
  }

  // the game's players edited in the project show once, as their entry ("was original"); ones only opened (or
  // changed back) list as the game's
  const sameAsGame = useSameAsGame()
  const mine = draft.players.filter((p) => !sameAsGame(p.uid))
  const edited = new Map(mine.filter((p) => p.original_id != null).map((p) => [p.original_id!, p]))

  // a team's players: the project's linked to it and the game's own (as the game has them)
  const filterKey: TeamKey | null = f.team.startsWith('new:') ? f.team.slice(4) : f.team.startsWith('orig:') ? Number(f.team.slice(5)) : null
  const inTeam = (r: Row) =>
    f.team === ALL ||
    (r.kind === 'project'
      ? f.team === FREE
        ? r.player.teams.length === 0
        : filterKey !== null && !!linkOf(r.player, filterKey)
      : typeof filterKey === 'number' && r.player.teams.includes(filterKey))
  const rows: Row[] = [
    ...mine.map((player) => ({ kind: 'project' as const, player })),
    ...(originals ?? []).filter((p) => !edited.has(p.id)).map((player) => ({ kind: 'original' as const, player })),
  ].filter(
    (r) =>
      matches(f.q, r.player.display_name, `${r.player.first_name} ${r.player.last_name}`, r.player.jersey_name) &&
      (f.origin === ALL || f.origin === r.kind) &&
      inTeam(r) &&
      (f.status === ALL || (f.status === 'hidden') === (r.kind === 'project' && !!r.player.hidden)),
  )
  const page = usePage(rows, list.page, list.pageSize)
  const projectUids = (rs: Row[]) => rs.flatMap((r) => (r.kind === 'project' ? [r.player.uid] : []))
  const selection = useListSelection(projectUids(page.rows), projectUids(rows))
  const picked = mine.filter((p) => selection.selected.has(p.uid)).map((p) => p.uid)
  // a new player leaves the project (and his places in the teams); an edited original goes back to the game's
  const deletePlayers = (uids: string[]) => uids.forEach((uid) => removePlayer(uid))

  const teamOptions = [
    { value: ALL, label: t('players.allTeams') },
    { value: FREE, label: t('players.freeAgents') },
    ...draft.teams
      .filter((tm) => tm.original_id == null)
      .map((tm) => ({ value: `new:${tm.uid}`, label: tm.name || t('team.unnamed'), group: t('players.newTeams') })),
    ...[...originalTeams]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((tm) => ({ value: `orig:${tm.id}`, label: tm.name, group: t('players.originalTeams') })),
  ]

  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.players')}</h1>
          <p className="text-sm text-muted-foreground">{t('players.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ShareImportButton kind="players" />
          <Button onClick={create}>
            <Plus /> {t('players.new')}
          </Button>
        </div>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('players.search')} />
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
        <FilterSelect value={f.team} onChange={(v) => list.set('team', v)} options={teamOptions} className="w-56" />
        <FilterSelect
          value={f.status}
          onChange={(v) => list.set('status', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.statusAll') },
            { value: 'visible', label: t('players.statusInPatch') },
            { value: 'hidden', label: t('teams.statusHidden') },
          ]}
        />
        <BulkActions kind="players" selection={selection} picked={picked} onDelete={deletePlayers} />
      </FilterBar>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('players.colTeam')}</TableHead>
            <TableHead>{t('players.colNumber')}</TableHead>
            <TableHead>{t('players.colPosition')}</TableHead>
            <TableHead className="text-center">{t('players.colFace')}</TableHead>
            <TableHead>{t('list.colId')}</TableHead>
            <DateHeads />
            <TableHead className="w-12" />
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={11} className="py-8 text-center text-muted-foreground">
                {originalsQuery.error
                  ? t('players.originalsFailed', { error: originalsQuery.error.message })
                  : originals === undefined
                    ? t('common.loading')
                    : t('players.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((r) => {
            if (r.kind === 'original') {
              const p = r.player
              return (
                <TableRow
                  key={p.id}
                  className="cursor-pointer text-muted-foreground"
                  title={t('players.editOriginalHint')}
                  onClick={() => navigate(playerPath(p.id), from)}
                >
                  <TableCell />
                  <TableCell data-grow>
                    <span className="flex items-center gap-2">
                      <OriginalPlayerAvatar player={p} />
                      <span className="text-foreground">{p.display_name}</span>
                      <OriginalBadge />
                    </span>
                  </TableCell>
                  <TableCell title={p.teams.map((id) => originalTeam.get(id)?.name ?? id).join(', ')}>
                    {p.teams.length ? (originalTeam.get(p.teams[0])?.name ?? p.teams[0]) : '—'}
                    {p.teams.length > 1 && <span className="ml-1 text-xs">+{p.teams.length - 1}</span>}
                  </TableCell>
                  <TableCell className="tabular-nums">{p.number ?? '—'}</TableCell>
                  <TableCell>{p.position !== null ? position.get(p.position) : '—'}</TableCell>
                  <YesNoCell value={!p.generic_head} title={t(p.generic_head ? 'players.faceGeneric' : 'players.faceGame')} />
                  <TableCell className="tabular-nums">{p.id}</TableCell>
                  <DateCells />
                  <TableCell />
                  <TableCell />
                </TableRow>
              )
            }
            const p = r.player
            return (
              <TableRow key={p.uid} className="cursor-pointer" onClick={() => navigate(playerPath(playerRef(p)), from)}>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <RowCheckbox selection={selection} value={p.uid} />
                </TableCell>
                <TableCell data-grow className={p.hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                  <span className="flex items-center gap-2">
                    <PlayerAvatar player={p} />
                    {p.display_name || `${p.first_name} ${p.last_name}`.trim() || (
                      <span className="text-muted-foreground">{t('common.unnamed')}</span>
                    )}
                    {p.original_id != null && <OriginalBadge entry={p.uid} />}
                    {p.hidden && <OutOfPatchBadge />}
                  </span>
                </TableCell>
                <TableCell className={p.teams.length ? '' : 'text-muted-foreground'} title={p.teams.map((l) => teamName(l.team)).join(', ')}>
                  {p.teams.length ? teamName(p.teams[0].team) : t('players.freeAgent')}
                  {p.teams.length > 1 && <span className="ml-1 text-xs text-muted-foreground">+{p.teams.length - 1}</span>}
                </TableCell>
                <TableCell className="tabular-nums">{p.teams[0]?.number ?? defaults[p.uid]?.number ?? '—'}</TableCell>
                <TableCell>
                  {(p.teams[0]?.position ?? defaults[p.uid]?.position) != null
                    ? position.get((p.teams[0]?.position ?? defaults[p.uid]?.position)!)
                    : '—'}
                </TableCell>
                <YesNoCell value={faceKind(p) !== 'players.faceGeneric'} title={t(faceKind(p))} />
                <TableCell className="tabular-nums text-muted-foreground">{p.original_id ?? p.player_id ?? t('common.auto')}</TableCell>
                <DateCells entry={p} />
                <TableCell>
                  <EntityIssues uid={p.uid} />
                </TableCell>
                <TableCell>
                  <span className="flex items-center justify-end gap-1">
                    <HideButton
                      hidden={!!p.hidden}
                      onToggle={() => updatePlayer(p.uid, { hidden: !p.hidden })}
                      hideHint={t('players.hideHint')}
                      showHint={t('players.showHint')}
                    />
                  </span>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </ScrollTable>
      <Pager page={page.page} pages={page.pages} total={page.total} pageSize={list.pageSize} onPage={list.setPage} />
      <SelectAllDialog selection={selection} />
    </div>
  )
}
