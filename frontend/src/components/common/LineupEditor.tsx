import { ArrowDown, ArrowUp, Plus, RotateCcw } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import type { Lineup, LineupMode, PlayerRef, Team } from '@/api/types'
import { EntityIssues, Field } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { type MessageKey, useI18n } from '@/i18n'
import { lineupOrder, modeKey, suggestLineup } from '@/lib/lineup'
import { useProject } from '@/state/project'
import { useCatalog, useLookups } from '@/state/queries'

const AUTO = 'auto'
const DEFAULT_MODE = modeKey(5, true)
const DEFAULT_TACTIC = 1 // the one every mode has
// slot areas (fs4positionareas, colors of the game's lineup screen)
const AREAS: Record<number, { label: MessageKey; color: string }> = {
  0: { label: 'lineup.areaGK', color: '#d77811' },
  1: { label: 'lineup.areaDEF', color: '#beaa00' },
  2: { label: 'lineup.areaATT', color: '#3c9abc' },
}
const TACTICS: Record<string, MessageKey> = { 0: 'lineup.tactic0', 1: 'lineup.tactic1', 2: 'lineup.tactic2' }
// modes seen in game with their own name
const MODE_NAMES: Record<string, MessageKey> = {
  [modeKey(5, true)]: 'lineup.modeDefault',
  [modeKey(4, false)]: 'lineup.modeLastManStanding',
  [modeKey(2, false)]: 'lineup.modePanna',
}

/** A player the lineup can use: project player (ref = uid) or one of the game's (ref = playerid). */
export interface LineupPlayer {
  ref: PlayerRef
  name: string
  position?: number | null
  avatar: ReactNode
}

function AreaBadge({ area }: { area: number }) {
  const { t } = useI18n()
  const a = AREAS[area]
  return (
    <span className="inline-flex w-12 justify-center rounded px-1.5 py-0.5 text-xs font-bold text-white" style={{ background: a?.color ?? 'gray' }}>
      {a ? t(a.label) : area}
    </span>
  )
}

/** Starting lineup and tactic per game mode (fs4lineup). A mode left automatic gets the game's pick. Players are
 * handled by string keys (String(ref)), mapped back to their refs when saved. */
export function LineupEditor({ team, players: roster }: { team: Team; players: LineupPlayer[] }) {
  const { t } = useI18n()
  const { updateTeam } = useProject()
  const { position: positionAbbr } = useLookups()
  const modes = useCatalog().data?.lineup_modes ?? []
  const [selected, setSelected] = useState(DEFAULT_MODE)
  const rosterUids = roster.map((p) => String(p.ref))
  const byUid = new Map(roster.map((p) => [String(p.ref), p]))
  const ref = (key: string) => byUid.get(key)?.ref ?? key
  const lineups = team.lineups ?? []
  const mode = modes.find((m) => modeKey(m.players, m.goalkeeper) === selected)
  const index = lineups.findIndex((l) => modeKey(l.players, l.goalkeeper) === selected)
  const stored = index >= 0 ? lineups[index] : undefined
  const keyed = (l: Lineup) => ({
    ...l,
    starters: l.starters.map((u) => (u == null ? null : String(u))),
    reserves: l.reserves.map(String),
  })
  const lineup = stored && keyed(stored)

  const modeLabel = (m: LineupMode) => {
    const key = modeKey(m.players, m.goalkeeper)
    const base = t(m.goalkeeper ? 'lineup.modeWithGK' : 'lineup.modeWithoutGK', { count: m.players })
    return MODE_NAMES[key] ? `${base} (${t(MODE_NAMES[key])})` : base
  }
  const setLineups = (next: Lineup[]) => updateTeam(team.uid, { lineups: next.length ? next : undefined })
  const setLineup = (patch: Partial<Lineup>) => setLineups(lineups.map((l, k) => (k === index ? { ...l, ...patch } : l)))

  const create = (m: LineupMode) => {
    // starts from the default mode's lineup when there is one (its goalkeeper left out of a mode without one)
    const main = lineups.find((l) => modeKey(l.players, l.goalkeeper) === DEFAULT_MODE)
    let base = main
      ? lineupOrder(keyed(main), rosterUids)
      : suggestLineup(
          roster.map((p) => ({ key: String(p.ref), position: p.position })),
          m.tactics[String(DEFAULT_TACTIC)] ?? [],
        )
    if (main && !m.goalkeeper) base = [...base.slice(1), ...base.slice(0, 1)]
    setLineups([
      ...lineups,
      {
        players: m.players,
        goalkeeper: m.goalkeeper,
        tactic: DEFAULT_TACTIC,
        starters: base.slice(0, m.players).map(ref),
        reserves: base.slice(m.players).map(ref),
      },
    ])
  }

  if (!mode) return null
  const tactics = Object.keys(mode.tactics)
  const areas = mode.tactics[String(lineup?.tactic ?? DEFAULT_TACTIC)] ?? mode.tactics[String(DEFAULT_TACTIC)] ?? []
  const order = lineup ? lineupOrder(lineup, rosterUids) : []
  const bench = order.slice(Math.min(mode.players, order.length))

  // picking a player already in another slot swaps the two
  const pick = (slot: number, uid: string | null) => {
    if (!lineup) return
    const starters = Array.from({ length: mode.players }, (_, k) => lineup.starters[k] ?? null)
    const other = uid ? starters.indexOf(uid) : -1
    if (other >= 0) starters[other] = starters[slot]
    starters[slot] = uid
    setLineup({ starters: starters.map((u) => (u == null ? null : ref(u))) })
  }
  const moveBench = (k: number, delta: number) => {
    const reserves = [...bench]
    ;[reserves[k], reserves[k + delta]] = [reserves[k + delta], reserves[k]]
    setLineup({ reserves: reserves.map(ref) })
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {t('lineup.title')} <EntityIssues uid={team.uid} />
          </CardTitle>
          <CardDescription>{t('lineup.description')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label={t('lineup.mode')}>
            <Select value={selected} onValueChange={setSelected}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {modes.map((m) => {
                  const key = modeKey(m.players, m.goalkeeper)
                  const set = lineups.some((l) => modeKey(l.players, l.goalkeeper) === key)
                  return (
                    <SelectItem key={key} value={key}>
                      {modeLabel(m)}
                      {set && <span className="text-muted-foreground"> · {t('lineup.modeSet')}</span>}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </Field>
          {lineup && tactics.length > 1 && (
            <Field label={t('lineup.tactic')} entity={team.uid} field={`lineups.${index}.tactic`}>
              <Select value={String(lineup.tactic)} onValueChange={(v) => setLineup({ tactic: Number(v) })}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {tactics.map((id) => (
                    <SelectItem key={id} value={id}>
                      {TACTICS[id] ? t(TACTICS[id]) : id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{modeLabel(mode)}</CardTitle>
          <CardDescription>
            {lineup ? t('lineup.setDescription') : t('lineup.autoDescription')}
            {lineup && tactics.length === 1 && ` ${t('lineup.singleTactic')}`}
          </CardDescription>
          <CardAction>
            {lineup ? (
              <Button variant="ghost" size="sm" onClick={() => setLineups(lineups.filter((_, k) => k !== index))}>
                <RotateCcw /> {t('lineup.backToAuto')}
              </Button>
            ) : (
              <Button size="sm" onClick={() => create(mode)} disabled={roster.length === 0}>
                <Plus /> {t('lineup.choose')}
              </Button>
            )}
          </CardAction>
        </CardHeader>
        {lineup && (
          <CardContent className="space-y-4">
            <div className="space-y-2">
              {areas.map((area, k) => {
                const chosen = lineup.starters[k]
                const valid = !!chosen && byUid.has(chosen)
                const filled = order[k]
                return (
                  <div key={k} className="flex items-center gap-3">
                    <AreaBadge area={area} />
                    <Select value={valid ? chosen! : AUTO} onValueChange={(v) => pick(k, v === AUTO ? null : v)}>
                      <SelectTrigger className="w-72">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={AUTO}>
                          {filled && !valid
                            ? t('lineup.autoSlotFilled', { name: byUid.get(filled)?.name ?? t('common.unnamed') })
                            : t('lineup.autoSlot')}
                        </SelectItem>
                        {roster.map((p) => (
                          <SelectItem key={String(p.ref)} value={String(p.ref)}>
                            {p.name}
                            {p.position != null && (
                              <span className="text-muted-foreground"> · {positionAbbr.get(p.position) ?? p.position}</span>
                            )}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {filled && byUid.get(filled)?.avatar}
                  </div>
                )
              })}
            </div>
            <div>
              <h3 className="mb-2 text-sm font-medium">{t('lineup.bench')}</h3>
              {bench.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('lineup.benchEmpty')}</p>
              ) : (
                <ol className="divide-y rounded-md border">
                  {bench.map((uid, k) => (
                    <li key={uid} className="flex items-center gap-3 px-3 py-1.5 text-sm">
                      <span className="w-5 text-muted-foreground">{k + 1}</span>
                      {byUid.get(uid)?.avatar}
                      <span className="flex-1">{byUid.get(uid)?.name ?? t('common.unnamed')}</span>
                      <Button variant="ghost" size="icon" disabled={k === 0} onClick={() => moveBench(k, -1)} title={t('lineup.moveUp')}>
                        <ArrowUp />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        disabled={k === bench.length - 1}
                        onClick={() => moveBench(k, 1)}
                        title={t('lineup.moveDown')}
                      >
                        <ArrowDown />
                      </Button>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  )
}
