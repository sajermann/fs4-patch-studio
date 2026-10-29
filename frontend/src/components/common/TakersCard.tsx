import { CornerUpLeft, CornerUpRight, Crown, Goal, type LucideIcon, MoveUpRight, Target } from 'lucide-react'
import type { PlayerRef, TakerRole } from '@/api/types'
import { Field } from '@/components/common/form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableCell, TableHead } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import type { MessageKey } from '@/i18n/pt-BR'
import type { Role } from '@/lib/teams'

const ROLES: { role: Role; label: MessageKey; icon: LucideIcon }[] = [
  { role: 'captain', label: 'takers.captainRole', icon: Crown },
  { role: 'penalty', label: 'takers.penalty', icon: Target },
  { role: 'free_kick', label: 'takers.freeKick', icon: Goal },
  { role: 'long_free_kick', label: 'takers.longFreeKick', icon: MoveUpRight },
  { role: 'left_corner', label: 'takers.leftCorner', icon: CornerUpLeft },
  { role: 'right_corner', label: 'takers.rightCorner', icon: CornerUpRight },
]
const CAPTAIN = 'captain'

/** Header cells of the role columns of a roster table (one icon per role). */
export function RoleHeads() {
  const { t } = useI18n()
  return ROLES.map(({ role, label, icon: Icon }) => (
    <TableHead key={role} className="w-8 px-1 text-center" title={t(label)}>
      <Icon className="mx-auto size-4" aria-label={t(label)} />
    </TableHead>
  ))
}

/** Role cells of one roster row: the role's icon where the player has it. */
export function RoleCells({ player, roles }: { player: PlayerRef; roles: Record<Role, PlayerRef | undefined> }) {
  const { t } = useI18n()
  return ROLES.map(({ role, label, icon: Icon }) => (
    <TableCell key={role} className="px-1 text-center">
      {roles[role] === player && <Icon className="mx-auto size-4 text-primary" aria-label={t(label)} />}
    </TableCell>
  ))
}

/** Captain and who takes each set piece. A taker role left unset falls back to `fallback` (new team: the captain). */
export function TakersCard({
  entity,
  players,
  captain,
  takers,
  fallback,
  onCaptainChange,
  onChange,
}: {
  entity: string
  players: { value: PlayerRef; label: string }[]
  captain: PlayerRef | undefined
  takers: Partial<Record<TakerRole, PlayerRef>>
  fallback?: { label: string } // option shown for an unset role (new team: "Captain (name)")
  onCaptainChange: (captain: PlayerRef) => void
  onChange: (takers: Partial<Record<TakerRole, PlayerRef>>) => void
}) {
  const { t } = useI18n()
  const refOf = (value: string) => players.find((p) => String(p.value) === value)?.value
  const set = (role: TakerRole, value: string) => {
    const next = { ...takers }
    if (value === CAPTAIN) delete next[role]
    else next[role] = refOf(value)
    onChange(next)
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('takers.title')}</CardTitle>
        <CardDescription>{t('takers.description')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        {ROLES.map(({ role, label, icon: Icon }) => {
          const value = role === 'captain' ? captain : takers[role as TakerRole]
          return (
            <Field
              key={role}
              label={
                <span className="flex items-center gap-1.5">
                  <Icon className="size-4" /> {t(label)}
                </span>
              }
              entity={entity}
              field={role === 'captain' ? 'captain' : `takers.${role}`}
            >
              <Select
                value={value !== undefined ? String(value) : CAPTAIN}
                onValueChange={(v) => {
                  if (role !== 'captain') set(role as TakerRole, v)
                  else if (refOf(v) !== undefined) onCaptainChange(refOf(v)!)
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {role !== 'captain' && fallback && <SelectItem value={CAPTAIN}>{fallback.label}</SelectItem>}
                  {players.map((p) => (
                    <SelectItem key={String(p.value)} value={String(p.value)}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )
        })}
      </CardContent>
    </Card>
  )
}
