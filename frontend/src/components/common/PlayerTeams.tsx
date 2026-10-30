import { ExternalLink, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Player, TeamLink } from '@/api/types'
import { FieldIssues, NumberInput } from '@/components/common/form'
import { PositionSelect, TeamSelect } from '@/components/common/Roster'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { useJoinTeam, useTeamName } from '@/lib/members'
import { leaveTeam, linkedTeam, playerName, playerRef } from '@/lib/players'
import { useIssues, usePlayerDefaults, useProject } from '@/state/project'
import { useCatalog, useLookups } from '@/state/queries'

/** Issues of one link row (team, number, position). */
function LinkIssues({ player, index }: { player: string; index: number }) {
  const issues = useIssues(player).filter((i) => i.field === `teams.${index}` || i.field?.startsWith(`teams.${index}.`))
  return <FieldIssues issues={issues} />
}

/** The player's clubs and national teams (TeamLink): each with its own number and position. Adding a team that is
 * full asks who leaves it (useJoinTeam). */
export function PlayerTeamsCard({ player }: { player: Player }) {
  const { t } = useI18n()
  const { draft, setDraft, updatePlayer } = useProject()
  const { position: positionAbbr } = useLookups()
  const catalog = useCatalog().data
  const defaults = usePlayerDefaults(player.uid)
  const teamName = useTeamName()
  const { join, dialog } = useJoinTeam()
  const from = useFrom(playerName(player, t('nav.players')))
  const ref = playerRef(player)
  const teamsIssues = useIssues(player.uid, 'teams')

  const setLink = (index: number, patch: Partial<TeamLink>) =>
    updatePlayer(player.uid, { teams: player.teams.map((l, k) => (k === index ? { ...l, ...patch } : l)) })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('playerEdit.teams')}</CardTitle>
        <CardDescription>{t('playerEdit.teamsDescription')}</CardDescription>
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
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {player.teams.map((l, k) => {
                const inherited = defaults?.team === l.team ? defaults : undefined
                const team = linkedTeam(draft, l.team)
                return (
                  <TableRow key={String(l.team)} className="align-top">
                    <TableCell className="whitespace-normal">
                      <span className="block truncate py-1.5 text-sm font-medium">{teamName(l.team)}</span>
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
                      <span className="flex">
                        {team && (
                          <Button variant="ghost" size="icon" asChild title={t('playerEdit.openTeam')}>
                            <Link to={`/teams/${team.uid}`} state={from.state}>
                              <ExternalLink />
                            </Link>
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" title={t('roster.removeFromTeam')} onClick={() => setDraft((p) => leaveTeam(p, ref, l.team))}>
                          <Trash2 />
                        </Button>
                      </span>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
        {player.teams.length === 0 && <p className="text-sm text-muted-foreground">{t('playerEdit.noTeams')}</p>}
        <div className="max-w-xs">
          <TeamSelect
            key={player.teams.length}
            exclude={player.teams.map((l) => l.team)}
            placeholder={t('playerEdit.addTeam')}
            onChange={(team) => void join(ref, team)}
          />
        </div>
        {dialog}
      </CardContent>
    </Card>
  )
}
