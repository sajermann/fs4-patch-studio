import { UserMinus, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { FriendlyMode, FriendlyPlayer, PlayerRef, WorldTour } from '@/api/types'
import { FieldIssues } from '@/components/common/form'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { AddPlayerDialog } from '@/components/common/Roster'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n, type MessageKey } from '@/i18n'
import { useFrom } from '@/lib/back'
import { useGamePlayers } from '@/lib/members'
import { playerName, playerOf, playerPath } from '@/lib/players'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'

type Side = keyof WorldTour

/** The most the game offers from each team (model.FRIENDLY_TEAM_SIZES); the user's captain is the fourth in Dark. */
const SIDES: { side: Side; size: number; name: MessageKey; note: MessageKey }[] = [
  { side: 'dark', size: 3, name: 'worldTour.team.dark', note: 'worldTour.team.darkNote' },
  { side: 'white', size: 4, name: 'worldTour.team.white', note: 'worldTour.team.whiteNote' },
]
const MODES: { mode: FriendlyMode; label: MessageKey; description: MessageKey }[] = [
  { mode: 'clone', label: 'worldTour.mode.clone', description: 'worldTour.mode.cloneDescription' },
  { mode: 'original', label: 'worldTour.mode.original', description: 'worldTour.mode.originalDescription' },
]

/** Clone or original for the next players added: what each one means is shown here, where the choice is made. */
function ModeChoice({ value, onChange }: { value: FriendlyMode; onChange: (mode: FriendlyMode) => void }) {
  const { t } = useI18n()
  return (
    <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t('worldTour.mode.label')}>
      {MODES.map((m) => (
        <button
          key={m.mode}
          type="button"
          role="radio"
          aria-checked={value === m.mode}
          onClick={() => onChange(m.mode)}
          className={cn(
            'rounded-md border p-3 text-left transition-colors hover:bg-muted/50',
            value === m.mode && 'border-primary bg-muted/50 ring-1 ring-primary',
          )}
        >
          <span className="block text-sm font-medium">{t(m.label)}</span>
          <span className="block text-xs text-muted-foreground">{t(m.description)}</span>
        </button>
      ))}
    </div>
  )
}

function SlotRow({ slot, onMode, onRemove }: { slot: FriendlyPlayer; onMode: (mode: FriendlyMode) => void; onRemove: () => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const gamePlayers = useGamePlayers()
  const from = useFrom(t('nav.worldTour'))
  const entry = playerOf(draft, slot.player)
  const game = typeof slot.player === 'number' ? gamePlayers.get(slot.player) : undefined
  return (
    <li className="flex items-center justify-between gap-2 py-2">
      <span className="flex min-w-0 items-center gap-2">
        {entry ? <PlayerAvatar player={entry} /> : game && <OriginalPlayerAvatar player={game} />}
        <Link to={playerPath(slot.player)} state={from.state} className="truncate font-medium underline-offset-4 hover:underline">
          {entry ? playerName(entry, t('common.unnamed')) : (game?.display_name ?? String(slot.player))}
        </Link>
      </span>
      <span className="flex shrink-0 items-center gap-1">
        <Select value={slot.mode ?? 'clone'} onValueChange={(v) => onMode(v as FriendlyMode)}>
          <SelectTrigger size="sm" className="w-28" aria-label={t('worldTour.mode.label')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODES.map((m) => (
              <SelectItem key={m.mode} value={m.mode}>
                {t(m.label)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="icon" title={t('worldTour.remove')} onClick={onRemove}>
          <UserMinus />
        </Button>
      </span>
    </li>
  )
}

/** Players of the World Tour friendly match (Project.world_tour): after that match the user can add them to the squad.
 * Places left empty get the game's random players. */
export function WorldTourPage() {
  const { t } = useI18n()
  const { draft, setDraft, issues } = useProject()
  const [adding, setAdding] = useState<Side>()
  const [mode, setMode] = useState<FriendlyMode>('clone')
  const slotsOf = (side: Side) => draft.world_tour?.[side] ?? []
  const picked = new Set<PlayerRef>(SIDES.flatMap(({ side }) => slotsOf(side).map((s) => s.player)))
  const setSlots = (side: Side, slots: (current: FriendlyPlayer[]) => FriendlyPlayer[]) =>
    setDraft((p) => ({ ...p, world_tour: { ...p.world_tour, [side]: slots(p.world_tour?.[side] ?? []) } }))
  const current = SIDES.find((s) => s.side === adding)

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('nav.worldTour')}</h1>
        <p className="text-sm text-muted-foreground">{t('worldTour.description')}</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t('worldTour.howTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>{t('worldTour.mode.cloneHelp')}</p>
          <p>{t('worldTour.mode.originalHelp')}</p>
          <p className="text-muted-foreground">{t('worldTour.emptyPlaces')}</p>
          <p className="text-muted-foreground">{t('worldTour.newSave')}</p>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {SIDES.map(({ side, size, name, note }) => {
          const slots = slotsOf(side)
          const free = size - slots.length
          return (
            <Card key={side}>
              <CardHeader>
                <CardTitle>
                  {t(name)}{' '}
                  <span className="font-normal text-muted-foreground">
                    ({slots.length}/{size})
                  </span>
                </CardTitle>
                <CardDescription>{t(note)}</CardDescription>
                <CardAction>
                  <Button variant="outline" size="sm" disabled={free <= 0} onClick={() => setAdding(side)}>
                    <UserPlus /> {t('roster.addPlayer')}
                  </Button>
                </CardAction>
              </CardHeader>
              <CardContent>
                <FieldIssues issues={issues.filter((i) => i.field === `world_tour.${side}`)} />
                {slots.length > 0 && (
                  <ul className="divide-y">
                    {slots.map((slot) => (
                      <SlotRow
                        key={String(slot.player)}
                        slot={slot}
                        onMode={(m) => setSlots(side, (list) => list.map((s) => (s.player === slot.player ? { ...s, mode: m } : s)))}
                        onRemove={() => setSlots(side, (list) => list.filter((s) => s.player !== slot.player))}
                      />
                    ))}
                  </ul>
                )}
                {free > 0 && <p className="pt-2 text-sm text-muted-foreground">{t('worldTour.freePlaces', { count: free })}</p>}
              </CardContent>
            </Card>
          )
        })}
      </div>
      <AddPlayerDialog
        open={!!adding}
        onOpenChange={(open) => !open && setAdding(undefined)}
        title={current ? t('worldTour.addTitle', { team: t(current.name) }) : ''}
        description={current ? t('worldTour.addDescription', { count: current.size - slotsOf(current.side).length }) : ''}
        header={<ModeChoice value={mode} onChange={setMode} />}
        exclude={picked}
        keepOpen
        disabled={!!current && slotsOf(current.side).length >= current.size}
        onPick={(ref) => adding && setSlots(adding, (list) => [...list, { player: ref, mode }])}
      />
    </div>
  )
}
