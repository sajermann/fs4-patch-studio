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
import { newUid, useProject } from '@/state/project'
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
  const full = draft.leagues.filter((l) => !l.hidden).length >= maxLeagues

  const create = () => {
    if (full) return
    const uid = newUid('lg')
    addLeague({ uid, name: '', sort_order: 6 })
    navigate(`/leagues/${uid}`, from)
  }

  const teamCount = (uid: string) => draft.teams.filter((t) => t.league === uid).length
  const originalLeagueOf = new Map(originalTeams.map((t) => [t.id, t.league]))
  const newInOriginal = (id: number) =>
    draft.teams.filter((t) => t.league === id && (t.original_id == null || originalLeagueOf.get(t.original_id) !== id))
      .length

  const list = useListParams(['q', 'origin', 'status'] as const)
  const f = list.values
  const isHidden = (r: Row) => (r.kind === 'project' ? !!r.league.hidden : r.league.hidden || isLeagueHidden(r.league.id))
  const rows: Row[] = [
    ...draft.leagues.map((league) => ({ kind: 'project' as const, league })),
    ...originals.map((league) => ({ kind: 'original' as const, league })),
  ].filter(
    (r) =>
      matches(f.q, r.league.name, r.league.short_name) &&
      (f.origin === ALL || f.origin === r.kind) &&
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
              return (
                <TableRow key={l.uid} className="cursor-pointer" onClick={() => navigate(`/leagues/${l.uid}`, from)}>
                  <TableCell data-grow className={l.hidden ? 'font-medium text-muted-foreground' : 'font-medium'}>
                    {l.name || <span className="text-muted-foreground">{t('common.unnamed')}</span>}
                    {l.hidden && <OutOfPatchBadge />}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">{l.league_id ?? t('common.auto')}</TableCell>
                  <TableCell className="tabular-nums">{l.sort_order}</TableCell>
                  <TableCell className="tabular-nums">{teamCount(l.uid)}</TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1">
                      <EntityIssues uid={l.uid} />
                      <HideButton
                        hidden={!!l.hidden}
                        onToggle={() => updateLeague(l.uid, { hidden: !l.hidden })}
                        hideHint={t('leagues.hideHint')}
                        showHint={t('leagues.showHint')}
                      />
                    </span>
                  </TableCell>
                </TableRow>
              )
            }
            const l = r.league
            return (
              <TableRow key={l.id} className="cursor-pointer text-muted-foreground" onClick={() => navigate(`/leagues/${l.id}`, from)}>
                <TableCell data-grow>
                  <span className="mr-2 text-foreground">{l.name}</span>
                  <OriginalBadge />
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
                  {l.team_count}
                  {newInOriginal(l.id) > 0 && <span className="text-foreground"> +{newInOriginal(l.id)}</span>}
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
