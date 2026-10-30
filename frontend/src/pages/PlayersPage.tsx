import { Loader2, Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { OriginalPlayer, Player, TeamKey } from '@/api/types'
import { EntityIssues, OriginalBadge } from '@/components/common/form'
import { HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
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
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { useGamePlayerEntry, useTeamName } from '@/lib/members'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { linkOf } from '@/lib/players'
import { newUid, useProject } from '@/state/project'
import { useLookups, useOriginalPlayers, useOriginalTeams } from '@/state/queries'

type Row = { kind: 'project'; player: Player } | { kind: 'original'; player: OriginalPlayer }

const FREE = 'free'
const ALL_ORIGINALS = { limit: 5000 } // the whole list (2,213 players) once: filtered here with the project's

export function PlayersPage() {
  const { t } = useI18n()
  const { draft, addPlayer, updatePlayer, defaults } = useProject()
  const { position, originalTeam } = useLookups()
  const originalTeams = useOriginalTeams().data ?? []
  const originals = useOriginalPlayers(ALL_ORIGINALS).data?.items
  const navigate = useNavigate()
  const from = useFrom(t('nav.players'))
  const list = useListParams(['q', 'origin', 'team', 'status'] as const)
  const f = list.values
  const teamName = useTeamName()

  const create = () => {
    const uid = newUid('jg')
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

  // the game's players edited in the project show once, as their entry ("was original")
  const edited = new Map(draft.players.filter((p) => p.original_id != null).map((p) => [p.original_id!, p]))
  const ensure = useGamePlayerEntry()
  const [opening, setOpening] = useState<number>()
  const openOriginal = async (id: number) => {
    if (opening !== undefined) return
    setOpening(id)
    const entry = await ensure(id)
    setOpening(undefined)
    if (entry) navigate(`/players/${entry.uid}`, from)
  }

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
    ...draft.players.map((player) => ({ kind: 'project' as const, player })),
    ...(originals ?? []).filter((p) => !edited.has(p.id)).map((player) => ({ kind: 'original' as const, player })),
  ].filter(
    (r) =>
      matches(f.q, r.player.display_name, `${r.player.first_name} ${r.player.last_name}`, r.player.jersey_name) &&
      (f.origin === ALL || f.origin === r.kind) &&
      inTeam(r) &&
      (f.status === ALL || (f.status === 'hidden') === (r.kind === 'project' && !!r.player.hidden)),
  )
  const page = usePage(rows, list.page, list.pageSize)

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.players')}</h1>
          <p className="text-sm text-muted-foreground">{t('players.description')}</p>
        </div>
        <Button onClick={create}>
          <Plus /> {t('players.new')}
        </Button>
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
      </FilterBar>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('players.colTeam')}</TableHead>
            <TableHead>{t('players.colNumber')}</TableHead>
            <TableHead>{t('players.colPosition')}</TableHead>
            <TableHead>{t('list.colId')}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                {originals === undefined ? t('common.loading') : t('players.noneFiltered')}
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
                  onClick={() => void openOriginal(p.id)}
                >
                  <TableCell data-grow>
                    <span className="flex items-center gap-2">
                      <OriginalPlayerAvatar player={p} />
                      <span className="text-foreground">{p.display_name}</span>
                      <OriginalBadge />
                      {opening === p.id && <Loader2 className="size-4 animate-spin" />}
                    </span>
                  </TableCell>
                  <TableCell title={p.teams.map((id) => originalTeam.get(id)?.name ?? id).join(', ')}>
                    {p.teams.length ? (originalTeam.get(p.teams[0])?.name ?? p.teams[0]) : '—'}
                    {p.teams.length > 1 && <span className="ml-1 text-xs">+{p.teams.length - 1}</span>}
                  </TableCell>
                  <TableCell className="tabular-nums">{p.number ?? '—'}</TableCell>
                  <TableCell>{p.position !== null ? position.get(p.position) : '—'}</TableCell>
                  <TableCell className="tabular-nums">{p.id}</TableCell>
                  <TableCell />
                </TableRow>
              )
            }
            const p = r.player
            return (
              <TableRow key={p.uid} className="cursor-pointer" onClick={() => navigate(`/players/${p.uid}`, from)}>
                <TableCell data-grow className={p.hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                  <span className="flex items-center gap-2">
                    <PlayerAvatar player={p} />
                    {p.display_name || `${p.first_name} ${p.last_name}`.trim() || (
                      <span className="text-muted-foreground">{t('common.unnamed')}</span>
                    )}
                    {p.original_id != null && <OriginalBadge edited />}
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
                <TableCell className="tabular-nums text-muted-foreground">{p.original_id ?? p.player_id ?? t('common.auto')}</TableCell>
                <TableCell>
                  <span className="flex items-center gap-1">
                    <EntityIssues uid={p.uid} />
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
    </div>
  )
}
