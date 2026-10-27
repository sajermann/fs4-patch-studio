import { ArrowDown, ArrowUp, Plus, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import type { Lineup, LineupMode, Player, Team } from '@/api/types'
import { EntityIssues, Field } from '@/components/common/form'
import { PlayerAvatar } from '@/components/common/PlayerPhoto'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { type MessageKey, useI18n } from '@/i18n'
import { lineupOrder, modeKey } from '@/lib/lineup'
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

const playerName = (p: Player | undefined, fallback: string) =>
  (p && (p.display_name || `${p.first_name} ${p.last_name}`.trim())) || fallback

function AreaBadge({ area }: { area: number }) {
  const { t } = useI18n()
  const a = AREAS[area]
  return (
    <span className="inline-flex w-12 justify-center rounded px-1.5 py-0.5 text-xs font-bold text-white" style={{ background: a?.color ?? 'gray' }}>
      {a ? t(a.label) : area}
    </span>
  )
}

/** Starting lineup and tactic per game mode (fs4lineup). A mode left automatic gets the game's pick. */
export function LineupEditor({ team }: { team: Team }) {
  const { t } = useI18n()
  const { draft, updateTeam, defaults } = useProject()
  const { position: positionAbbr } = useLookups()
  const modes = useCatalog().data?.lineup_modes ?? []
  const [selected, setSelected] = useState(DEFAULT_MODE)
  const roster = draft.players.filter((p) => p.team === team.uid && !p.hidden)
  const rosterUids = roster.map((p) => p.uid)
  const byUid = new Map(roster.map((p) => [p.uid, p]))
  const lineups = team.lineups ?? []
  const mode = modes.find((m) => modeKey(m.players, m.goalkeeper) === selected)
  const index = lineups.findIndex((l) => modeKey(l.players, l.goalkeeper) === selected)
  const lineup = index >= 0 ? lineups[index] : undefined

  const position = (p: Player) => p.position ?? defaults[p.uid]?.position
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
    let base = main ? lineupOrder(main, rosterUids) : rosterUids
    if (main && !m.goalkeeper) base = [...base.slice(1), ...base.slice(0, 1)]
    setLineups([
      ...lineups,
      { players: m.players, goalkeeper: m.goalkeeper, tactic: DEFAULT_TACTIC, starters: base.slice(0, m.players), reserves: base.slice(m.players) },
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
    setLineup({ starters })
  }
  const moveBench = (k: number, delta: number) => {
    const reserves = [...bench]
    ;[reserves[k], reserves[k + delta]] = [reserves[k + delta], reserves[k]]
    setLineup({ reserves })
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
                            ? t('lineup.autoSlotFilled', { name: playerName(byUid.get(filled), t('common.unnamed')) })
                            : t('lineup.autoSlot')}
                        </SelectItem>
                        {roster.map((p) => (
                          <SelectItem key={p.uid} value={p.uid}>
                            {playerName(p, t('common.unnamed'))}
                            {position(p) != null && (
                              <span className="text-muted-foreground"> · {positionAbbr.get(position(p)!) ?? position(p)}</span>
                            )}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {filled && <PlayerAvatar player={byUid.get(filled)!} />}
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
                      <PlayerAvatar player={byUid.get(uid)!} />
                      <span className="flex-1">{playerName(byUid.get(uid), t('common.unnamed'))}</span>
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
