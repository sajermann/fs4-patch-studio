import { Plus, UserMinus, UserPlus } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { OriginalPlayer, PlayerRef, Team, TeamKey, TeamLink } from '@/api/types'
import { EntityIssues, FieldIssues, NumberInput, OriginalBadge } from '@/components/common/form'
import { OutOfPatchBadge } from '@/components/common/HideButton'
import { matches, SearchInput } from '@/components/common/list'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { RoleCells, RoleHeads, TakersCard } from '@/components/common/TakersCard'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { type Member, useGamePlayerEntry, useJoinTeam, useTeamMembers, useTeamName } from '@/lib/members'
import { firstFreeNumber, leaveTeam, linkOf, playerName, playerRef, teamKey, teamsWith } from '@/lib/players'
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

/** Dialog: project players not in the team yet (free agents first; the game's players edited in the project too). */
function ProjectPlayerPicker({ team, open, onOpenChange, onPick }: { team: TeamKey; open: boolean; onOpenChange: (o: boolean) => void; onPick: (ref: PlayerRef) => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const teamName = useTeamName()
  const [q, setQ] = useState('')
  const candidates = draft.players
    .filter((p) => !linkOf(p, team) && matches(q, playerName(p, ''), p.jersey_name))
    .sort((a, b) => Number(a.teams.length > 0) - Number(b.teams.length > 0))
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('roster.addProjectPlayerTitle')}</DialogTitle>
          <DialogDescription>{t('roster.addProjectPlayerDescription')}</DialogDescription>
        </DialogHeader>
        <SearchInput value={q} onChange={setQ} placeholder={t('players.search')} />
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('roster.noProjectPlayers')}</p>
        ) : (
          <ul className="max-h-96 divide-y overflow-y-auto">
            {candidates.map((p) => (
              <li key={p.uid} className="flex items-center justify-between gap-2 py-2">
                <span className="flex min-w-0 items-center gap-2">
                  <PlayerAvatar player={p} />
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5 truncate">
                      {playerName(p, t('common.unnamed'))}
                      {p.original_id != null && <OriginalBadge edited />}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {p.teams.length ? p.teams.map((l) => teamName(l.team)).join(', ') : t('players.freeAgent')}
                    </span>
                  </span>
                </span>
                <Button size="sm" variant="outline" onClick={() => onPick(playerRef(p))}>
                  {t('common.add')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Dialog: search the game's players (they keep their other teams and also play for this one). */
function GamePlayerPicker({ exclude, open, onOpenChange, onPick }: { exclude: Set<PlayerRef>; open: boolean; onOpenChange: (o: boolean) => void; onPick: (p: OriginalPlayer) => void }) {
  const { t } = useI18n()
  const teamName = useTeamName()
  const [q, setQ] = useState('')
  const found = useOriginalPlayers({ q: q || undefined, limit: 40 }, open).data?.items ?? []
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('roster.addGamePlayerTitle')}</DialogTitle>
          <DialogDescription>{t('roster.addGamePlayerDescription')}</DialogDescription>
        </DialogHeader>
        <SearchInput value={q} onChange={setQ} placeholder={t('players.search')} />
        <ul className="max-h-96 divide-y overflow-y-auto">
          {found.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2 py-2">
              <span className="flex min-w-0 items-center gap-2">
                <OriginalPlayerAvatar player={p} />
                <span className="min-w-0">
                  <span className="block truncate">{p.display_name}</span>
                  <span className="block truncate text-xs text-muted-foreground">{p.teams.map(teamName).join(', ') || '—'}</span>
                </span>
              </span>
              <Button size="sm" variant="outline" disabled={exclude.has(p.id)} onClick={() => onPick(p)}>
                {t('common.add')}
              </Button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
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
  const [projectOpen, setProjectOpen] = useState(false)
  const [gameOpen, setGameOpen] = useState(false)
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

  const setLink = (m: Member, patch: Partial<TeamLink>) => m.player && updatePlayer(m.player.uid, { teams: teamsWith(m.player, key, patch) })
  const remove = async (m: Member) => {
    if (m.kind === 'squad' && !(await ensure(m.ref as number))) return
    setDraft((p) => leaveTeam(p, m.ref, key))
  }
  const createPlayer = () => {
    const uid = newUid('jg')
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
              <Button variant="outline" size="sm" onClick={() => setProjectOpen(true)}>
                <UserPlus /> {t('roster.addProjectPlayer')}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setGameOpen(true)}>
                <UserPlus /> {t('roster.addGamePlayer')}
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
                  {m.kind === 'squad' ? (
                    <>
                      <TableCell className="tabular-nums">{m.number ?? '—'}</TableCell>
                      <TableCell>{m.position != null ? (positionAbbr.get(m.position) ?? m.position) : '—'}</TableCell>
                    </>
                  ) : (
                    <>
                      <TableCell>
                        <NumberInput
                          value={linkOf(m.player!, key)?.number ?? undefined}
                          onChange={(v) => setLink(m, { number: v })}
                          min={1}
                          max={99}
                          className="h-8"
                          placeholder={inheritedNumber(m)}
                        />
                      </TableCell>
                      <TableCell>
                        <PositionSelect value={linkOf(m.player!, key)?.position} placeholder={inheritedPosition(m)} onChange={(v) => setLink(m, { position: v })} />
                      </TableCell>
                    </>
                  )}
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
        <ProjectPlayerPicker
          team={key}
          open={projectOpen}
          onOpenChange={setProjectOpen}
          onPick={(ref) => {
            setProjectOpen(false)
            void join(ref, key)
          }}
        />
        <GamePlayerPicker
          exclude={new Set(members.map((m) => m.ref))}
          open={gameOpen}
          onOpenChange={setGameOpen}
          onPick={(p) => {
            setGameOpen(false)
            void join(p.id, key)
          }}
        />
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
          {m.player ? (
            <Link
              to={`/players/${m.player.uid}`}
              state={from}
              className={cn('font-medium underline-offset-4 hover:underline', m.hidden && 'text-muted-foreground')}
            >
              {m.name}
            </Link>
          ) : (
            <span className="text-muted-foreground">{m.name}</span>
          )}
          {m.kind === 'edited' && <OriginalBadge edited />}
          {m.hidden && <OutOfPatchBadge />}
        </span>
      </TableCell>
      {children}
    </TableRow>
  )
}

/** Team select for a player's link: the project's new teams and the game's teams (edited ones by their new name);
 * teams the player is already in are left out (except `value`). */
export function TeamSelect({
  value,
  exclude,
  placeholder,
  onChange,
}: {
  value?: TeamKey
  exclude: TeamKey[]
  placeholder?: string
  onChange: (team: TeamKey) => void
}) {
  const { t } = useI18n()
  const { draft } = useProject()
  const originals = useOriginalTeams().data ?? []
  const teamName = useTeamName()
  const encode = (v: TeamKey) => (typeof v === 'string' ? `new:${v}` : `orig:${v}`)
  const shown = (k: TeamKey) => k === value || !exclude.includes(k)
  const games = [...originals].map((o) => ({ id: o.id, name: teamName(o.id) })).sort((a, b) => a.name.localeCompare(b.name))
  return (
    <Select value={value === undefined ? '' : encode(value)} onValueChange={(v) => onChange(v.startsWith('new:') ? v.slice(4) : Number(v.slice(5)))}>
      <SelectTrigger size="sm" className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {draft.teams.some((tm) => tm.original_id == null) && (
          <SelectGroup>
            <SelectLabel>{t('players.newTeams')}</SelectLabel>
            {draft.teams
              .filter((tm) => tm.original_id == null && shown(tm.uid))
              .map((tm) => (
                <SelectItem key={tm.uid} value={encode(tm.uid)}>
                  {tm.name || t('team.unnamed')}
                </SelectItem>
              ))}
          </SelectGroup>
        )}
        <SelectGroup>
          <SelectLabel>{t('players.originalTeams')}</SelectLabel>
          {games
            .filter((g) => shown(g.id))
            .map((g) => (
              <SelectItem key={g.id} value={encode(g.id)}>
                {g.name}
              </SelectItem>
            ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}
