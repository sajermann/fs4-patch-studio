import { ChevronRight, FileUp, PackageOpen, Search } from 'lucide-react'
import { useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from '@/lib/notify'
import { ApiError, api } from '@/api/client'
import type { League, PackageInspect, Player, ShareKind, Team } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useI18n, type MessageKey } from '@/i18n'
import { analyzeShare, entryName, keepKnownTeams, mergeShared, type SharedEntry } from '@/lib/share'
import { useFitImported } from '@/lib/members'
import { fitImportedLeagues } from '@/lib/teams'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useCatalog, useOriginalTeams } from '@/state/queries'
import { problemText } from './share'

const KINDS: ShareKind[] = ['leagues', 'teams', 'players']
const DEFAULT_PREFIX = 'fifa14-'
const NO_LEAGUE = '__no_league__'
const NO_TEAM = '__no_team__'

type Picked = Record<ShareKind, Set<string>>

const fold = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()

/** The package as a tree: each league with its teams, each team with its players; teams without a league of the
 * package and players without a team of the package in groups of their own. A team in two leagues (or a player in
 * two teams) shows under both, with one checkbox state. */
function buildTree(found: PackageInspect) {
  const leagues = (found.kinds.leagues?.items ?? []) as League[]
  const teams = (found.kinds.teams?.items ?? []) as Team[]
  const players = (found.kinds.players?.items ?? []) as Player[]
  const leagueUids = new Set(leagues.map((l) => l.uid))
  const teamUids = new Set(teams.map((t) => t.uid))
  const teamsOf = new Map<string, Team[]>()
  for (const t of teams) {
    const mine = t.leagues.filter((l): l is string => typeof l === 'string' && leagueUids.has(l))
    for (const l of mine.length ? mine : [NO_LEAGUE]) teamsOf.set(l, [...(teamsOf.get(l) ?? []), t])
  }
  const playersOf = new Map<string, Player[]>()
  for (const p of players) {
    const mine = p.teams.map((l) => l.team).filter((t): t is string => typeof t === 'string' && teamUids.has(t))
    for (const t of mine.length ? mine : [NO_TEAM]) playersOf.set(t, [...(playersOf.get(t) ?? []), p])
  }
  return { leagues, teams, players, teamsOf, playersOf }
}

/** "Import package": a FIFA patch package (.fifapkg.zip, made by an external extractor) converted for this game by
 * the backend, picked item by item in a tree (league → teams → players: each checkbox marks only its own item, and a
 * "select all" row under each level marks the level below), then imported in one go: leagues, teams, players, each
 * kind merged the way its own zip import merges it. The uid prefix keeps the ids of the source game apart from other
 * packages'. */
export function PackageImportButton() {
  const { t } = useI18n()
  const { draft, setDraft, requestSave } = useProject()
  const fitImported = useFitImported()
  const originalTeams = useOriginalTeams().data ?? []
  const maxLeagueTeams = useCatalog().data?.max_league_teams ?? 30
  const input = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [prefix, setPrefix] = useState(DEFAULT_PREFIX)
  const [file, setFile] = useState<File | null>(null)
  const [found, setFound] = useState<PackageInspect | null>(null)
  const [picked, setPicked] = useState<Picked>({ leagues: new Set(), teams: new Set(), players: new Set() })
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)

  const tree = useMemo(() => (found ? buildTree(found) : null), [found])
  // what each item replaces in the project as it is now
  const replaces = useMemo(() => {
    const out = new Set<string>()
    if (found)
      for (const k of KINDS) {
        const items = found.kinds[k]?.items ?? []
        for (const uid of analyzeShare(k, draft, items).replaces.keys()) out.add(`${k}:${uid}`)
      }
    return out
  }, [found, draft])

  const reset = () => {
    setOpen(false)
    setFile(null)
    setFound(null)
    setQuery('')
  }
  const read = async (f: File, p: string) => {
    setBusy(true)
    try {
      const result = await api.inspectPackage(f, p)
      const all = (k: ShareKind) => new Set((result.kinds[k]?.items ?? []).map((i) => i.uid))
      setFound(result)
      setPicked({ leagues: all('leagues'), teams: all('teams'), players: all('players') })
      setExpanded(new Set((result.kinds.leagues?.items ?? []).map((l) => `league:${l.uid}`)))
    } catch (e) {
      setFound(null)
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const set = (kind: ShareKind, uids: string[], on: boolean) =>
    setPicked((p) => {
      const next = new Set(p[kind])
      for (const u of uids) {
        if (on) next.add(u)
        else next.delete(u)
      }
      return { ...p, [kind]: next }
    })
  const toggleOpen = (key: string) =>
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const apply = async () => {
    if (!found) return
    setBusy(true)
    try {
      const got: Partial<Record<ShareKind, SharedEntry[]>> = {}
      for (const k of KINDS) {
        const part = found.kinds[k]
        const uids = (part?.items ?? []).map((i) => i.uid).filter((u) => picked[k].has(u))
        if (part && uids.length) got[k] = (await api.applyShare<SharedEntry>(k, part.token, uids)).items
      }
      const fit = got.players ? await fitImported(got.players as Player[]) : undefined
      // every kind merged in order on the same project: the teams find the leagues, the players the teams (a link to
      // an item left out is dropped, as in any zip import)
      setDraft((start) => {
        let project = start
        for (const k of KINDS) {
          let items = got[k]
          if (!items) continue
          if (k === 'players') items = keepKnownTeams(project, items as Player[])
          const merged = mergeShared(k, project, items, analyzeShare(k, project, items))
          const uids = items.map((e) => e.uid)
          project =
            k === 'teams'
              ? fitImportedLeagues(project, merged, uids, originalTeams, maxLeagueTeams)
              : k === 'players' && fit
                ? fit(project, merged)
                : merged
        }
        return project
      })
      requestSave()
      toast.success(t('package.imported'), {
        description: KINDS.filter((k) => got[k]?.length)
          .map((k) => t(`package.count.${k}` as MessageKey, { count: got[k]!.length }))
          .join(' · '),
      })
      reset()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('share.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const problems = found ? KINDS.flatMap((k) => found.kinds[k]?.problems ?? []) : []
  const total = (k: ShareKind) => found?.kinds[k]?.items.length ?? 0
  const nothing = KINDS.every((k) => picked[k].size === 0)

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} title={t('package.hint')}>
        <PackageOpen /> {t('package.button')}
      </Button>
      <Dialog open={open} onOpenChange={(v) => !v && !busy && reset()}>
        <DialogContent width="lg" className="flex max-h-[90vh] flex-col overflow-hidden">
          <DialogHeader className="shrink-0">
            <DialogTitle>{t('package.title')}</DialogTitle>
            <DialogDescription>{t('package.description')}</DialogDescription>
          </DialogHeader>
          <div className="shrink-0 space-y-2 text-sm">
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
              <div className="space-y-1.5">
                <Label htmlFor="package-prefix">{t('package.prefix')}</Label>
                <Input
                  id="package-prefix"
                  value={prefix}
                  disabled={busy}
                  onChange={(e) => setPrefix(e.target.value)}
                  onBlur={() => file && found && void read(file, prefix)}
                />
              </div>
              <Button variant="outline" disabled={busy} onClick={() => input.current?.click()}>
                <FileUp /> {file ? t('package.otherFile') : t('package.pickFile')}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">{t('package.prefixHint')}</p>
            <input
              ref={input}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (f) {
                  setFile(f)
                  void read(f, prefix)
                }
              }}
            />
            {busy && !found && <p className="text-muted-foreground">{t('package.reading')}</p>}
          </div>
          {found && tree && (
            <>
              <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-md border bg-muted/40 p-2 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{found.summary.patch_name || file?.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {[found.summary.game, found.summary.credits && t('package.credits', { credits: found.summary.credits })].filter(Boolean).join(' · ')}
                  </p>
                </div>
                <div className="relative w-56">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('package.search')} className="h-8 pl-8" />
                </div>
              </div>
              <p className="shrink-0 text-xs text-muted-foreground">{t('package.order')}</p>
              <PackageTree tree={tree} picked={picked} set={set} expanded={expanded} toggleOpen={toggleOpen} replaces={replaces} query={query} />
              {problems.length > 0 && (
                <details className="shrink-0 text-sm">
                  <summary className="cursor-pointer font-medium">{t('share.problemsTitle', { count: problems.length })}</summary>
                  <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto">
                    {problems.map((p, k) => (
                      <li key={k}>
                        <span className="font-medium">{p.name || t('common.unnamed')}</span>: {problemText(t, p)}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <p className="shrink-0 text-sm">
                {t('package.summary', {
                  leagues: picked.leagues.size,
                  leaguesTotal: total('leagues'),
                  teams: picked.teams.size,
                  teamsTotal: total('teams'),
                  players: picked.players.size,
                  playersTotal: total('players'),
                })}
              </p>
            </>
          )}
          <DialogFooter className="shrink-0">
            <Button variant="outline" disabled={busy} onClick={reset}>
              {t('common.cancel')}
            </Button>
            <Button disabled={busy || !found || nothing} onClick={() => void apply()}>
              {t('package.confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

type Tree = ReturnType<typeof buildTree>

/** Checkbox state of a group: all, none or some (indeterminate). */
const groupState = (uids: string[], set: Set<string>): boolean | 'indeterminate' => {
  const n = uids.filter((u) => set.has(u)).length
  return n === 0 ? false : n === uids.length ? true : 'indeterminate'
}

function PackageTree({
  tree,
  picked,
  set,
  expanded,
  toggleOpen,
  replaces,
  query,
}: {
  tree: Tree
  picked: Picked
  set: (kind: ShareKind, uids: string[], on: boolean) => void
  expanded: Set<string>
  toggleOpen: (key: string) => void
  replaces: Set<string>
  query: string
}) {
  const { t } = useI18n()
  const q = fold(query.trim())
  const searching = q.length > 0
  const hit = (kind: ShareKind, e: SharedEntry) => fold(entryName(kind, e)).includes(q)
  const playersOf = (team: string) => tree.playersOf.get(team) ?? []
  const shownPlayers = (team: string) => playersOf(team).filter((p) => !searching || hit('players', p))
  const teamShown = (team: Team) => !searching || hit('teams', team) || shownPlayers(team.uid).length > 0
  const teamsOf = (league: string) => tree.teamsOf.get(league) ?? []
  const shownTeams = (league: string) => teamsOf(league).filter(teamShown)
  const leagueShown = (league: League) => !searching || hit('leagues', league) || shownTeams(league.uid).length > 0
  const isOpen = (key: string) => searching || expanded.has(key)

  const badge = (kind: ShareKind, uid: string) =>
    replaces.has(`${kind}:${uid}`) ? <span className="text-xs text-amber-700 dark:text-amber-400">{t('package.badgeReplaces')}</span> : null

  const teamNode = (team: Team, depth: number, key: string) => {
    const players = playersOf(team.uid)
    const shown = searching && !hit('teams', team) ? shownPlayers(team.uid) : players
    const open = isOpen(key)
    return (
      <div key={key}>
        <Row
          kind="teams"
          depth={depth}
          open={players.length ? open : undefined}
          onToggleOpen={() => toggleOpen(key)}
          checked={picked.teams.has(team.uid)}
          onCheck={(v) => set('teams', [team.uid], v)}
          label={entryName('teams', team) || t('common.unnamed')}
          extra={
            <>
              {badge('teams', team.uid)}
              {players.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums">
                  {t('package.teamPlayers', { picked: players.filter((p) => picked.players.has(p.uid)).length, total: players.length })}
                </span>
              )}
            </>
          }
        />
        {open && players.length > 0 && (
          <>
            <SelectAllRow
              depth={depth + 1}
              state={groupState(players.map((p) => p.uid), picked.players)}
              onCheck={(v) => set('players', players.map((p) => p.uid), v)}
              label={t('package.selectAllPlayers', { count: players.length })}
            />
            {shown.map((p) => (
              <Row
                kind="players"
                key={`${key}/${p.uid}`}
                depth={depth + 1}
                checked={picked.players.has(p.uid)}
                onCheck={(v) => set('players', [p.uid], v)}
                label={entryName('players', p) || t('common.unnamed')}
                extra={badge('players', p.uid)}
              />
            ))}
          </>
        )}
      </div>
    )
  }

  const teamGroup = (teams: Team[], depth: number, keyBase: string) => (
    <>
      {teams.length > 0 && (
        <SelectAllRow
          depth={depth}
          state={groupState(teams.map((tm) => tm.uid), picked.teams)}
          onCheck={(v) => set('teams', teams.map((tm) => tm.uid), v)}
          label={t('package.selectAllTeams', { count: teams.length })}
        />
      )}
      {teams.filter(teamShown).map((tm) => teamNode(tm, depth, `${keyBase}/team:${tm.uid}`))}
    </>
  )

  const looseTeams = teamsOf(NO_LEAGUE)
  const loosePlayers = playersOf(NO_TEAM)
  const shownLoosePlayers = loosePlayers.filter((p) => !searching || hit('players', p))
  return (
    <div className="min-h-0 flex-1 overflow-y-auto rounded-md border p-1 text-sm">
      {tree.leagues.filter(leagueShown).map((league) => {
        const key = `league:${league.uid}`
        const open = isOpen(key)
        return (
          <div key={key}>
            <Row
              kind="leagues"
              depth={0}
              strong
              open={teamsOf(league.uid).length ? open : undefined}
              onToggleOpen={() => toggleOpen(key)}
              checked={picked.leagues.has(league.uid)}
              onCheck={(v) => set('leagues', [league.uid], v)}
              label={entryName('leagues', league) || t('common.unnamed')}
              extra={
                <>
                  {badge('leagues', league.uid)}
                  <span className="text-xs text-muted-foreground tabular-nums">{t('package.leagueTeams', { count: teamsOf(league.uid).length })}</span>
                </>
              }
            />
            {open && teamGroup(teamsOf(league.uid), 1, key)}
          </div>
        )
      })}
      {looseTeams.filter(teamShown).length > 0 && (
        <div>
          <GroupTitle>{t('package.teamsWithoutLeague')}</GroupTitle>
          {teamGroup(looseTeams, 1, 'no-league')}
        </div>
      )}
      {shownLoosePlayers.length > 0 && (
        <div>
          <GroupTitle>{t('package.playersWithoutTeam')}</GroupTitle>
          <SelectAllRow
            depth={1}
            state={groupState(loosePlayers.map((p) => p.uid), picked.players)}
            onCheck={(v) => set('players', loosePlayers.map((p) => p.uid), v)}
            label={t('package.selectAllPlayers', { count: loosePlayers.length })}
          />
          {shownLoosePlayers.map((p) => (
            <Row
              kind="players"
              key={`no-team/${p.uid}`}
              depth={1}
              checked={picked.players.has(p.uid)}
              onCheck={(v) => set('players', [p.uid], v)}
              label={entryName('players', p) || t('common.unnamed')}
              extra={badge('players', p.uid)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

const INDENT = ['pl-1', 'pl-7', 'pl-13']

const KIND_TONE: Record<ShareKind, string> = {
  leagues: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  teams: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  players: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
}

/** One item of the tree: its checkbox marks only this item; the caret (when it has children) opens it. */
function Row({
  kind,
  depth,
  checked,
  onCheck,
  label,
  extra,
  open,
  onToggleOpen,
  strong,
}: {
  kind: ShareKind
  depth: number
  checked: boolean
  onCheck: (v: boolean) => void
  label: string
  extra?: ReactNode
  open?: boolean // undefined = no children
  onToggleOpen?: () => void
  strong?: boolean
}) {
  const { t } = useI18n()
  return (
    <div
      className={cn('flex items-center gap-2 rounded py-1 pr-2 hover:bg-accent/50', INDENT[depth], open !== undefined && 'cursor-pointer')}
      onClick={() => open !== undefined && onToggleOpen?.()}
    >
      <ChevronRight className={cn('size-4 shrink-0 text-muted-foreground transition-transform', open === undefined && 'invisible', open && 'rotate-90')} />
      <span onClick={(e) => e.stopPropagation()} className="flex">
        <Checkbox checked={checked} onCheckedChange={(v) => onCheck(v === true)} aria-label={label} />
      </span>
      <span className={cn('w-[4.5rem] shrink-0 rounded px-1.5 py-0.5 text-center whitespace-nowrap text-[10px] font-medium uppercase', KIND_TONE[kind])}>
        {t(`package.kind.${kind}` as MessageKey)}
      </span>
      <span className={cn('min-w-0 flex-1 truncate', strong && 'font-medium')}>{label}</span>
      {extra}
    </div>
  )
}

/** "Select all …" under a level: marks or unmarks every item of the level below (and nothing else). */
function SelectAllRow({ depth, state, onCheck, label }: { depth: number; state: boolean | 'indeterminate'; onCheck: (v: boolean) => void; label: string }) {
  return (
    <label className={cn('flex cursor-pointer items-center gap-2 py-1 pr-2 text-xs text-muted-foreground', INDENT[depth])}>
      <span className="size-4 shrink-0" />
      <Checkbox checked={state} onCheckedChange={() => onCheck(state !== true)} />
      {label}
    </label>
  )
}

function GroupTitle({ children }: { children: ReactNode }) {
  return <p className="px-2 pt-3 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">{children}</p>
}
