import { Plus, UserMinus, UserPlus } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { PlayerRef, Team, TeamKey, TeamLink } from '@/api/types'
import { EntityIssues, FieldIssues, NumberInput, OriginalBadge } from '@/components/common/form'
import { OutOfPatchBadge } from '@/components/common/HideButton'
import { matches } from '@/components/common/list'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { RoleCells, RoleHeads, TakersCard } from '@/components/common/TakersCard'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { type Member, useGamePlayerEntry, useJoinTeam, useTeamMembers, useTeamName } from '@/lib/members'
import { firstFreeNumber, leaveTeam, linkOf, playerName, playerOf, playerPath, playerRef, teamKey, teamsWith } from '@/lib/players'
import { effectiveRoles } from '@/lib/teams'
import { cn } from '@/lib/utils'
import { newUid, useIssues, useProject } from '@/state/project'
import { useCatalog, useLookups, useOriginalPlayers, useOriginalTeams } from '@/state/queries'

const AUTO = 'auto'

export function PositionSelect({ value, placeholder, onChange }: { value?: number | null; placeholder: string; onChange: (v: number | undefined) => void }) {
  const catalog = useCatalog().data
  return (
    <Select value={value == null ? AUTO : String(value)} onValueChange={(v) => onChange(v === AUTO ? undefined : Number(v))}>
      <SelectTrigger size="sm" className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={AUTO}>{placeholder}</SelectItem>
        {(catalog?.positions ?? []).map((pos) => (
          <SelectItem key={pos.code} value={String(pos.code)}>
            {pos.abbr}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Dialog: players not in the team yet, in two groups: the project's (free agents first; the game's players edited
 * in the project too) and the game's (search; they keep their other teams). Picking one closes it (a full team then
 * asks who leaves). */
function AddPlayerDialog({ team, open, onOpenChange, onPick }: { team: TeamKey; open: boolean; onOpenChange: (o: boolean) => void; onPick: (ref: PlayerRef) => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const teamName = useTeamName()
  const [q, setQ] = useState('')
  const found = useOriginalPlayers({ q: q || undefined, limit: 40 }, open).data?.items ?? []
  const project = draft.players
    .filter((p) => !linkOf(p, team) && matches(q, playerName(p, ''), p.jersey_name))
    .sort((a, b) => Number(a.teams.length > 0) - Number(b.teams.length > 0))
    .map((p): PickerItem<PlayerRef> => ({
      key: playerRef(p),
      icon: <PlayerAvatar player={p} />,
      title: (
        <span className="flex items-center gap-1.5">
          {playerName(p, t('common.unnamed'))}
          {p.original_id != null && <OriginalBadge entry={p.uid} />}
        </span>
      ),
      subtitle: p.teams.length ? p.teams.map((l) => teamName(l.team)).join(', ') : t('players.freeAgent'),
    }))
  const game = found
    .filter((p) => !playerOf(draft, p.id)) // edited ones are in the project group
    .map((p): PickerItem<PlayerRef> => ({
      key: p.id,
      icon: <OriginalPlayerAvatar player={p} />,
      title: p.display_name,
      subtitle: p.teams.map(teamName).join(', ') || '—',
      disabled: p.teams.includes(team as number),
    }))
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('roster.addPlayerTitle')}
      description={t('roster.addPlayerDescription')}
      placeholder={t('players.search')}
      query={q}
      onQuery={setQ}
      groups={[
        { label: t('roster.projectPlayers'), items: project },
        { label: t('roster.gamePlayers'), items: game },
      ]}
      empty={t('roster.noPlayersFound')}
      onPick={(ref) => {
        onOpenChange(false)
        onPick(ref)
      }}
    />
  )
}

/** Roster of a team (new or edited original): the project's players (number and position of this team), the game's
 * players (an original team's own, or added; edited ones are project entries) and captain/set-piece takers below.
 * Adding to a full team asks who leaves it (useJoinTeam). */
export function RosterCard({ team }: { team: Team }) {
  const { t } = useI18n()
  const { setDraft, updatePlayer, updateTeam, addPlayer } = useProject()
  const { position: positionAbbr } = useLookups()
  const catalog = useCatalog().data
  const navigate = useNavigate()
  const from = useFrom(team.name || t('players.colTeam'))
  const [adding, setAdding] = useState(false)
  const ensure = useGamePlayerEntry()
  const { join, dialog } = useJoinTeam()
  const key = teamKey(team)
  const original = team.original_id != null
  const game = useOriginalTeams().data?.find((o) => o.id === team.original_id)
  const members = useTeamMembers(team)
  const active = members.filter((m) => !m.hidden)
  const max = catalog?.max_roster ?? 13
  const rosterIssues = useIssues(team.uid, 'players')
  const captain = team.captain ?? (original ? game?.captain : active[0]?.ref)
  const takers = { ...(original ? game?.takers : {}), ...team.takers }
  const roles = effectiveRoles(captain, takers)

  // number/position in this team; one of the game's players as the game has him gets his entry first (the change is
  // applied by playerid: typing fast may ask for his entry twice)
  const setLink = async (m: Member, patch: Partial<TeamLink>) => {
    if (m.player) return updatePlayer(m.player.uid, { teams: teamsWith(m.player, key, patch) })
    if (!(await ensure(m.ref as number))) return
    setDraft((p) => ({ ...p, players: p.players.map((pl) => (pl.original_id === m.ref ? { ...pl, teams: teamsWith(pl, key, patch) } : pl)) }))
  }
  const remove = async (m: Member) => {
    if (m.kind === 'squad' && !(await ensure(m.ref as number))) return
    setDraft((p) => leaveTeam(p, m.ref, key))
  }
  const createPlayer = () => {
    const uid = newUid()
    const number = firstFreeNumber(members.map((m) => m.number))
    addPlayer({ uid, teams: [{ team: key, number }], first_name: '', last_name: '', generic: true, skills: {}, appearance: {}, fields: {} })
    navigate(`/players/${uid}`, from)
  }
  const inheritedNumber = (m: Member) => (m.number != null ? t('common.inherited', { value: m.number }) : t('common.default'))
  const inheritedPosition = (m: Member) =>
    m.position != null ? t('common.inherited', { value: positionAbbr.get(m.position) ?? m.position }) : t('street.reset')

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>
            {t('teamEdit.roster')}{' '}
            <span className="font-normal text-muted-foreground">
              ({active.length}/{max})
            </span>
          </CardTitle>
          <CardDescription>{original ? t('teamEdit.originalRosterDescription') : t('teamEdit.rosterDescription')}</CardDescription>
          <CardAction>
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
                <UserPlus /> {t('roster.addPlayer')}
              </Button>
              {!original && (
                <Button size="sm" onClick={createPlayer} disabled={active.length >= max}>
                  <Plus /> {t('players.new')}
                </Button>
              )}
            </div>
          </CardAction>
        </CardHeader>
        <CardContent>
          <FieldIssues issues={rosterIssues} />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('list.colName')}</TableHead>
                <TableHead className="w-24">{t('teamEdit.number')}</TableHead>
                <TableHead className="w-32">{t('players.colPosition')}</TableHead>
                <RoleHeads />
                <TableHead className="w-20" />
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <MemberRow key={String(m.ref)} member={m} from={from.state}>
                  <TableCell>
                    <NumberInput
                      value={(m.player ? linkOf(m.player, key)?.number : m.number) ?? undefined}
                      onChange={(v) => void setLink(m, { number: v })}
                      min={1}
                      max={99}
                      className="h-8"
                      placeholder={inheritedNumber(m)}
                    />
                  </TableCell>
                  <TableCell>
                    <PositionSelect
                      value={m.player ? linkOf(m.player, key)?.position : m.position}
                      placeholder={inheritedPosition(m)}
                      onChange={(v) => void setLink(m, { position: v })}
                    />
                  </TableCell>
                  <RoleCells player={m.ref} roles={roles} />
                  <TableCell>{m.player && <EntityIssues uid={m.player.uid} />}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" title={t('roster.removeFromTeam')} onClick={() => void remove(m)}>
                      <UserMinus />
                    </Button>
                  </TableCell>
                </MemberRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
        <AddPlayerDialog team={key} open={adding} onOpenChange={setAdding} onPick={(ref) => void join(ref, key)} />
        {dialog}
      </Card>
      <TakersCard
        entity={team.uid}
        players={active.map((m) => ({ value: m.ref, label: m.name }))}
        captain={captain}
        takers={takers}
        fallback={original ? undefined : { label: t('takers.captain', { name: active.find((m) => m.ref === captain)?.name ?? '—' }) }}
        onCaptainChange={(c) => updateTeam(team.uid, { captain: c })}
        onChange={(takers) => updateTeam(team.uid, { takers })}
      />
    </div>
  )
}

function MemberRow({ member: m, from, children }: { member: Member; from: unknown; children: ReactNode }) {
  return (
    <TableRow>
      <TableCell>
        <span className="flex items-center gap-2">
          {m.avatar}
          <Link
            to={playerPath(m.ref)}
            state={from}
            className={cn('font-medium underline-offset-4 hover:underline', m.hidden && 'text-muted-foreground')}
          >
            {m.name}
          </Link>
          {m.kind !== 'project' && <OriginalBadge entry={m.player?.uid} />}
          {m.hidden && <OutOfPatchBadge />}
        </span>
      </TableCell>
      {children}
    </TableRow>
  )
}
