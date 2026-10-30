import { Eye, EyeOff, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { League, OriginalLeague } from '@/api/types'
import { EntityIssues, OriginalBadge } from '@/components/common/form'
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
import { GameHiddenBadge, HideButton, OutOfPatchBadge } from '@/components/common/HideButton'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { useOriginalChanges } from '@/lib/originals'
import { leagueKey, leaguePath } from '@/lib/players'
import { newLeagues } from '@/lib/teams'
import { newUid, useProject, useSameAsGame } from '@/state/project'
import { useCatalog, useOriginalLeagues, useOriginalTeams } from '@/state/queries'

type Row = { kind: 'project'; league: League } | { kind: 'original'; league: OriginalLeague }

export function LeaguesPage() {
  const { t } = useI18n()
  const { draft, addLeague, updateLeague } = useProject()
  const originals = useOriginalLeagues().data ?? []
  const originalTeams = useOriginalTeams().data ?? []
  const navigate = useNavigate()
  const from = useFrom(t('nav.leagues'))
  const { isLeagueHidden, toggleLeague } = useOriginalChanges()
  const maxLeagues = useCatalog().data?.max_leagues ?? 39
  // hidden leagues stay out of the patch: they do not take one of the game's free image numbers
  const full = newLeagues(draft).filter((l) => !l.hidden).length >= maxLeagues

  const create = () => {
    if (full) return
    const uid = newUid()
    addLeague({ uid, name: '', sort_order: 6 })
    navigate(leaguePath(uid), from)
  }

  const teamCount = (uid: string) => draft.teams.filter((t) => t.leagues.includes(uid)).length
  const originalLeagueOf = new Map(originalTeams.map((t) => [t.id, t.league]))
  // a game league's teams change: how many joined minus how many left (a team's leagues live in the team)
  const teamsDelta = (id: number) =>
    draft.teams.filter((t) => {
      const inGame = t.original_id != null && originalLeagueOf.get(t.original_id) === id
      return t.leagues.includes(id) !== inGame
    }).reduce((n, t) => n + (t.leagues.includes(id) ? 1 : -1), 0)

  const originalById = new Map(originals.map((l) => [l.id, l]))
  // teams of a row: a new league's, or a game league's (its own + the ones the project adds - the ones it takes out)
  const teamsOf = (l: League) =>
    l.original_id == null ? teamCount(l.uid) : (originalById.get(l.original_id)?.team_count ?? 0) + teamsDelta(l.original_id)

  // the game's leagues edited in the project show once, as their entry ("was original"); ones only opened (or
  // changed back) list as the game's
  const sameAsGame = useSameAsGame()
  const mine = draft.leagues.filter((l) => !sameAsGame(l.uid))
  const edited = new Set(mine.filter((l) => l.original_id != null).map((l) => l.original_id!))

  const list = useListParams(['q', 'origin', 'status'] as const)
  const f = list.values
  const isHidden = (r: Row) =>
    r.kind === 'project'
      ? r.league.original_id != null
        ? isLeagueHidden(r.league.original_id)
        : !!r.league.hidden
      : r.league.hidden || isLeagueHidden(r.league.id)
  const rows: Row[] = [
    ...mine.map((league) => ({ kind: 'project' as const, league })),
    ...originals.filter((l) => !edited.has(l.id)).map((league) => ({ kind: 'original' as const, league })),
  ].filter(
    (r) =>
      matches(f.q, r.league.name, r.league.short_name) &&
      (f.origin === ALL ||
        f.origin === r.kind ||
        (f.origin === 'original' && r.kind === 'project' && r.league.original_id != null)) &&
      (f.status === ALL || (f.status === 'hidden') === isHidden(r)),
  )
  const page = usePage(rows, list.page, list.pageSize)

  return (
    <div className={LIST_PAGE}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('nav.leagues')}</h1>
          <p className="text-sm text-muted-foreground">{t('leagues.description')}</p>
        </div>
        <Button
          onClick={create}
          disabled={full}
          title={full ? t('leagues.maxReached', { max: maxLeagues }) : undefined}
        >
          <Plus /> {t('leagues.new')}
        </Button>
      </div>
      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('leagues.search')} />
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
        <FilterSelect
          value={f.status}
          onChange={(v) => list.set('status', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.statusAll') },
            { value: 'visible', label: t('list.statusInGame') },
            { value: 'hidden', label: t('leagues.statusHidden') },
          ]}
        />
      </FilterBar>
      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('list.colId')}</TableHead>
            <TableHead>{t('leagues.colOrder')}</TableHead>
            <TableHead>{t('nav.teams')}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                {t('leagues.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((r) => {
            if (r.kind === 'project') {
              const l = r.league
              const oid = l.original_id
              const hidden = isHidden(r)
              return (
                <TableRow key={l.uid} className="cursor-pointer" onClick={() => navigate(leaguePath(leagueKey(l)), from)}>
                  <TableCell data-grow className={hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                    <span className="mr-2">{l.name || <span className="text-muted-foreground">{t('common.unnamed')}</span>}</span>
                    {oid != null && <OriginalBadge entry={l.uid} league={oid} />}
                    {oid != null && isLeagueHidden(oid) ? (
                      <Badge variant="outline" className="ml-1 font-normal">
                        {t('leagues.hiddenByProject')}
                      </Badge>
                    ) : (
                      l.hidden && <OutOfPatchBadge />
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">{oid ?? l.league_id ?? t('common.auto')}</TableCell>
                  <TableCell className="tabular-nums">{l.sort_order}</TableCell>
                  <TableCell className="tabular-nums">{teamsOf(l)}</TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1">
                      <EntityIssues uid={l.uid} />
                      {oid != null ? (
                        <HideButton
                          hidden={isLeagueHidden(oid)}
                          onToggle={() => toggleLeague(oid)}
                          hideHint={t('leagues.originalHideHint')}
                          showHint={t('leagues.originalShowHint')}
                        />
                      ) : (
                        <HideButton
                          hidden={!!l.hidden}
                          onToggle={() => updateLeague(l.uid, { hidden: !l.hidden })}
                          hideHint={t('leagues.hideHint')}
                          showHint={t('leagues.showHint')}
                        />
                      )}
                    </span>
                  </TableCell>
                </TableRow>
              )
            }
            const l = r.league
            return (
              <TableRow key={l.id} className="cursor-pointer text-muted-foreground" onClick={() => navigate(leaguePath(l.id), from)}>
                <TableCell data-grow>
                  <span className="mr-2 text-foreground">{l.name}</span>
                  <OriginalBadge league={l.id} />
                  {l.hidden && <GameHiddenBadge />}
                  {isLeagueHidden(l.id) && (
                    <Badge variant="outline" className="ml-1 font-normal">
                      {t('leagues.hiddenByProject')}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="tabular-nums">{l.id}</TableCell>
                <TableCell className="tabular-nums">{l.sort_order}</TableCell>
                <TableCell className="tabular-nums">
                  {l.team_count + teamsDelta(l.id)}
                </TableCell>
                <TableCell>
                  {!l.hidden && (
                    <Button
                      variant="ghost"
                      size="sm"
                      title={
                        isLeagueHidden(l.id) ? t('leagues.originalShowHint') : t('leagues.originalHideHint')
                      }
                      onClick={(e) => {
                        e.stopPropagation()
                        toggleLeague(l.id)
                      }}
                    >
                      {isLeagueHidden(l.id) ? <Eye /> : <EyeOff />} {isLeagueHidden(l.id) ? t('list.show') : t('list.hide')}
                    </Button>
                  )}
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
