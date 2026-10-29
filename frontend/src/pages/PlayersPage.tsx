import { Plus } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { OriginalPlayer, Player } from '@/api/types'
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
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { newUid, useProject } from '@/state/project'
import { useLookups, useOriginalPlayers, useOriginalTeams } from '@/state/queries'

type Row = { kind: 'project'; player: Player } | { kind: 'original'; player: OriginalPlayer }

const FREE = 'free'
const ALL_ORIGINALS = { limit: 5000 } // the whole list (2,213 players) once: filtered here with the project's

export function PlayersPage() {
  const { t } = useI18n()
  const { draft, addPlayer, updatePlayer } = useProject()
  const { position, originalTeam } = useLookups()
  const originalTeams = useOriginalTeams().data ?? []
  const originals = useOriginalPlayers(ALL_ORIGINALS).data?.items
  const navigate = useNavigate()
  const from = useFrom(t('nav.players'))
  const list = useListParams(['q', 'origin', 'team', 'status'] as const)
  const f = list.values
  const teamName = useMemo(() => new Map(draft.teams.map((tm) => [tm.uid, tm.name || t('team.unnamed')])), [draft.teams, t])

  const create = () => {
    const uid = newUid('jg')
    addPlayer({
      uid,
      team: f.team.startsWith('new:') ? f.team.slice(4) : null,
      first_name: '',
      last_name: '',
      generic: true,
      skills: {},
      appearance: {},
      fields: {},
    })
    navigate(`/players/${uid}`, from)
  }

  const inTeam = (r: Row) =>
    f.team === ALL ||
    (r.kind === 'project'
      ? f.team === FREE
        ? !r.player.team
        : f.team === `new:${r.player.team}`
      : f.team.startsWith('orig:') && r.player.teams.includes(Number(f.team.slice(5))))
  const rows: Row[] = [
    ...draft.players.map((player) => ({ kind: 'project' as const, player })),
    ...(originals ?? []).map((player) => ({ kind: 'original' as const, player })),
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
                <TableRow key={p.id} className="text-muted-foreground">
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
                    {p.hidden && <OutOfPatchBadge />}
                  </span>
                </TableCell>
                <TableCell className={p.team ? '' : 'text-muted-foreground'}>
                  {p.team ? teamName.get(p.team) : t('players.freeAgent')}
                </TableCell>
                <TableCell className="tabular-nums">{p.number ?? '—'}</TableCell>
                <TableCell>{p.position !== undefined ? position.get(p.position) : '—'}</TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{p.player_id ?? t('common.auto')}</TableCell>
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
