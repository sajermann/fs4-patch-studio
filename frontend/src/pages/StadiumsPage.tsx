import { Lock, LockOpen } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { OriginalStadium } from '@/api/types'
import { BallThumb } from '@/components/common/BallThumb'
import { ALL, FilterBar, FilterSelect, LIST_PAGE, matches, Pager, ScrollTable, SearchInput, useListParams, usePage } from '@/components/common/list'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { ballName, gameBallName, pickedBall } from '@/lib/balls'
import { useOriginalChanges } from '@/lib/originals'
import { GAME_MODES, menuVersion, modesOf, stadiumPath } from '@/lib/stadiums'
import { useProject } from '@/state/project'
import { useOriginalBalls, useOriginalStadiums } from '@/state/queries'

export function StadiumsPage() {
  const { t } = useI18n()
  const { draft } = useProject()
  const stadiums = useOriginalStadiums().data ?? []
  const gameBalls = useOriginalBalls().data ?? []
  const { stadiumLocked, setStadiumLocked } = useOriginalChanges()
  const navigate = useNavigate()
  const from = useFrom(t('nav.stadiums'))
  const list = useListParams(['q', 'mode', 'status', 'ball'] as const)
  const f = list.values
  const picked = draft.originals?.stadium_balls ?? {}
  const balls = draft.balls ?? []

  /** The ball of an ordinary match in a stadium (the version the game's menus list). */
  const ballOf = (s: OriginalStadium) => {
    const ref = pickedBall(draft, menuVersion(s))
    const own = typeof ref === 'string' ? balls.find((b) => b.uid === ref) : balls.find((b) => b.original_id === ref)
    const game = typeof ref === 'number' ? gameBalls.find((b) => b.id === ref) : undefined
    const name = own?.name.trim()
      ? ballName(own, '')
      : typeof ref === 'number'
        ? gameBallName(game, ref, (id) => t('balls.gameName', { id }))
        : t('common.unnamed')
    return { name, own, id: typeof ref === 'number' ? ref : undefined }
  }
  const changedBall = (s: OriginalStadium) => s.versions.some((v) => v.id in picked)

  const rows = stadiums.filter((s) => {
    const locked = stadiumLocked(s)
    return (
      matches(f.q, s.name, String(s.id), ballOf(s).name) &&
      (f.mode === ALL || (s.in_menu && s.filters.includes(Number(f.mode)))) &&
      (f.status === ALL ||
        (f.status === 'locked' && locked) ||
        (f.status === 'unlocked' && !locked) ||
        (f.status === 'changed' && s.lockable_id != null && locked !== s.locked)) &&
      (f.ball === ALL || (f.ball === 'changed') === changedBall(s))
    )
  })
  const page = usePage(rows, list.page, list.pageSize)

  return (
    <div className={LIST_PAGE}>
      <div>
        <h1 className="text-2xl font-semibold">{t('nav.stadiums')}</h1>
        <p className="text-sm text-muted-foreground">{t('stadiums.description')}</p>
      </div>

      <FilterBar active={list.active} onClear={list.clear}>
        <SearchInput value={f.q} onChange={(v) => list.set('q', v)} placeholder={t('stadiums.search')} />
        <FilterSelect
          value={f.mode}
          onChange={(v) => list.set('mode', v)}
          className="w-48"
          options={[{ value: ALL, label: t('stadiums.modeAll') }, ...GAME_MODES.map((m) => ({ value: String(m.filter), label: t(m.label) }))]}
        />
        <FilterSelect
          value={f.status}
          onChange={(v) => list.set('status', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('list.statusAll') },
            { value: 'locked', label: t('stadiums.statusLocked') },
            { value: 'unlocked', label: t('stadiums.statusUnlocked') },
            { value: 'changed', label: t('stadiums.statusChanged') },
          ]}
        />
        <FilterSelect
          value={f.ball}
          onChange={(v) => list.set('ball', v)}
          className="w-44"
          options={[
            { value: ALL, label: t('stadiums.ballAll') },
            { value: 'changed', label: t('stadiums.ballChanged') },
            { value: 'game', label: t('stadiums.ballGame') },
          ]}
        />
      </FilterBar>

      <ScrollTable>
        <TableHeader>
          <TableRow>
            <TableHead data-grow>{t('list.colName')}</TableHead>
            <TableHead>{t('stadiums.colModes')}</TableHead>
            <TableHead>{t('stadiums.colBall')}</TableHead>
            <TableHead>{t('stadiums.colStatus')}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {page.total === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                {t('stadiums.noneFiltered')}
              </TableCell>
            </TableRow>
          )}
          {page.rows.map((s) => {
            const locked = stadiumLocked(s)
            const modes = modesOf(s)
            const shown = ballOf(s)
            return (
              <TableRow key={s.id} className="cursor-pointer" onClick={() => navigate(stadiumPath(s.id), from)}>
                <TableCell data-grow className="font-medium">
                  {s.name}
                  {s.versions.length > 1 && (
                    <span className="ml-2 text-xs font-normal text-muted-foreground">{t('stadiums.versions', { count: s.versions.length })}</span>
                  )}
                </TableCell>
                <TableCell>
                  <span className="flex flex-wrap gap-1">
                    {modes.length ? (
                      modes.map((m) => (
                        <Badge key={m.filter} variant="secondary" className="font-normal">
                          {t(m.label)}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-xs text-muted-foreground">{s.in_menu ? t('stadiums.customOnly') : t('stadiums.notInMenus')}</span>
                    )}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="flex items-center gap-2" title={shown.name}>
                    <BallThumb ball={shown.own} id={shown.id} className="size-7 rounded-full" />
                    <span className="max-w-48 truncate text-sm">{shown.name}</span>
                    {changedBall(s) && <span className="text-xs text-muted-foreground">{t('stadiums.changed')}</span>}
                  </span>
                </TableCell>
                <TableCell>
                  {s.lockable_id != null ? (
                    <>
                      <Badge variant={locked ? 'outline' : 'secondary'} className="font-normal">
                        {locked ? t('stadiums.locked') : t('stadiums.unlocked')}
                      </Badge>
                      {locked !== s.locked && <span className="ml-2 text-xs text-muted-foreground">{t('stadiums.changed')}</span>}
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">{t('stadiums.alwaysUnlocked')}</span>
                  )}
                </TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  {s.lockable_id != null && (
                    <Button variant="outline" size="sm" onClick={() => setStadiumLocked(s, !locked)}>
                      {locked ? <LockOpen /> : <Lock />} {locked ? t('list.unlock') : t('list.lock')}
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
