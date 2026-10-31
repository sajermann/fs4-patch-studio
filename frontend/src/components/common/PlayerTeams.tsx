import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Player, TeamKey, TeamLink } from '@/api/types'
import { FieldIssues, NumberInput, OriginalCrest, TeamCrest } from '@/components/common/form'
import { matches } from '@/components/common/list'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import { PositionSelect } from '@/components/common/Roster'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { useJoinTeam, useTeamName } from '@/lib/members'
import { leaveTeam, playerName, playerRef, teamPath } from '@/lib/players'
import { useIssues, usePlayerDefaults, useProject } from '@/state/project'
import { editedOriginals, useLeagueName } from '@/lib/teams'
import { useCatalog, useLookups, useOriginalTeams } from '@/state/queries'

/** Dialog: every team the player is not in (the project's new ones, then the game's, edited ones by their entry),
 * with crests, their leagues and a search. Picking one closes it (a full team then asks who leaves). */
function AddTeamDialog({ player, open, onOpenChange, onPick }: { player: Player; open: boolean; onOpenChange: (o: boolean) => void; onPick: (team: TeamKey) => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const originals = useOriginalTeams().data ?? []
  const leagueName = useLeagueName()
  const [q, setQ] = useState('')
  const edited = editedOriginals(draft)
  const mine = new Set(player.teams.map((l) => l.team))
  const leaguesOf = (leagues: (number | string)[]) => (leagues.length ? leagues.map(leagueName).join(', ') : leagueName(null))
  const byName = (a: { title: string }, b: { title: string }) => a.title.localeCompare(b.title)
  const newTeams = draft.teams
    .filter((tm) => tm.original_id == null && !mine.has(tm.uid) && matches(q, tm.name))
    .map((tm) => ({ key: tm.uid as TeamKey, icon: <TeamCrest team={tm} />, title: tm.name || t('common.unnamed'), subtitle: leaguesOf(tm.leagues) }))
    .sort(byName)
  const gameTeams = originals
    .filter((o) => !mine.has(o.id))
    .map((o) => {
      const entry = edited.get(o.id)
      return entry
        ? { key: o.id as TeamKey, icon: <TeamCrest team={entry} />, title: entry.name, subtitle: leaguesOf(entry.leagues) }
        : { key: o.id as TeamKey, icon: <OriginalCrest team={o} />, title: o.name, subtitle: leaguesOf(o.league === null ? [] : [o.league]) }
    })
    .filter((c) => matches(q, c.title))
    .sort(byName)
  return (
    <PickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('playerEdit.addTeamTitle')}
      description={t('playerEdit.addTeamDescription')}
      placeholder={t('teams.search')}
      query={q}
      onQuery={setQ}
      groups={[
        { label: t('players.newTeams'), items: newTeams as PickerItem<TeamKey>[] },
        { label: t('players.originalTeams'), items: gameTeams as PickerItem<TeamKey>[] },
      ]}
      empty={t('leagueEdit.noTeamsFound')}
      onPick={(team) => {
        onOpenChange(false)
        onPick(team)
      }}
    />
  )
}

/** Issues of one link row (team, number, position). */
function LinkIssues({ player, index }: { player: string; index: number }) {
  const issues = useIssues(player).filter((i) => i.field === `teams.${index}` || i.field?.startsWith(`teams.${index}.`))
  return <FieldIssues issues={issues} />
}

/** The player's clubs and national teams (TeamLink): each with its own number and position. Adding a team that is
 * full asks who leaves it (useJoinTeam). */
export function PlayerTeamsCard({ player }: { player: Player }) {
  const { t } = useI18n()
  const { setDraft, updatePlayer } = useProject()
  const { position: positionAbbr } = useLookups()
  const catalog = useCatalog().data
  const defaults = usePlayerDefaults(player.uid)
  const teamName = useTeamName()
  const { join, dialog } = useJoinTeam()
  const from = useFrom(playerName(player, t('nav.players')))
  const ref = playerRef(player)
  const teamsIssues = useIssues(player.uid, 'teams')
  const [adding, setAdding] = useState(false)

  const setLink = (index: number, patch: Partial<TeamLink>) =>
    updatePlayer(player.uid, { teams: player.teams.map((l, k) => (k === index ? { ...l, ...patch } : l)) })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('playerEdit.teams')}</CardTitle>
        <CardDescription>{t('playerEdit.teamsDescription')}</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            <Plus /> {t('playerEdit.addTeam')}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <FieldIssues issues={teamsIssues} />
        {player.teams.length > 0 && (
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead>{t('players.colTeam')}</TableHead>
                <TableHead className="w-24">{t('teamEdit.number')}</TableHead>
                <TableHead className="w-32">{t('players.colPosition')}</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {player.teams.map((l, k) => {
                const inherited = defaults?.team === l.team ? defaults : undefined
                return (
                  <TableRow key={String(l.team)} className="align-top">
                    <TableCell className="whitespace-normal">
                      <Link
                        to={teamPath(l.team)}
                        state={from.state}
                        className="inline-block max-w-full truncate py-1.5 align-top text-sm font-medium underline-offset-4 hover:underline"
                      >
                        {teamName(l.team)}
                      </Link>
                      <LinkIssues player={player.uid} index={k} />
                    </TableCell>
                    <TableCell>
                      <NumberInput
                        value={l.number ?? undefined}
                        onChange={(v) => setLink(k, { number: v })}
                        min={catalog?.ranges.number[0] ?? 1}
                        max={catalog?.ranges.number[1] ?? 99}
                        className="h-8"
                        placeholder={inherited?.number != null ? t('common.inherited', { value: inherited.number }) : t('common.auto')}
                      />
                    </TableCell>
                    <TableCell>
                      <PositionSelect
                        value={l.position}
                        onChange={(v) => setLink(k, { position: v })}
                        placeholder={
                          inherited?.position != null
                            ? t('common.inherited', { value: positionAbbr.get(inherited.position) ?? inherited.position })
                            : t('common.auto')
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" title={t('roster.removeFromTeam')} onClick={() => setDraft((p) => leaveTeam(p, ref, l.team))}>
                        <X />
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
        {player.teams.length === 0 && <p className="text-sm text-muted-foreground">{t('playerEdit.noTeams')}</p>}
        <AddTeamDialog player={player} open={adding} onOpenChange={setAdding} onPick={(team) => void join(ref, team)} />
        {dialog}
      </CardContent>
    </Card>
  )
}
