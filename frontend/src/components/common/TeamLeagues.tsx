import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { LeagueKey, Team } from '@/api/types'
import { LeagueIcon } from '@/components/common/LeagueIcon'
import { matches } from '@/components/common/list'
import { PickerDialog, type PickerItem } from '@/components/common/PickerDialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { FieldIssues } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { useFrom } from '@/lib/back'
import { leaguePath } from '@/lib/players'
import { newLeagues, useLeagueName, useLeagueTeams } from '@/lib/teams'
import { useIssues, useProject } from '@/state/project'
import { useOriginalLeagues } from '@/state/queries'

/** The leagues a team plays in (one leagueteamlinks row each): image, name (link to the league), a button that takes
 * the team out of one league (confirmed) and an "Add league" dialog (new leagues and the game's, with a search). */
export function TeamLeagues({ team }: { team: Team }) {
  const { t } = useI18n()
  const { draft, updateTeam } = useProject()
  const originals = (useOriginalLeagues().data ?? []).filter((l) => !l.hidden)
  const leagueName = useLeagueName()
  const leagueTeams = useLeagueTeams()
  const from = useFrom(team.name || t('teams.new'))
  const [adding, setAdding] = useState(false)
  const [q, setQ] = useState('')
  const [leaving, setLeaving] = useState<LeagueKey>()
  const issues = useIssues(team.uid).filter((i) => i.field === 'leagues' || i.field?.startsWith('leagues.'))

  const item = (key: LeagueKey): PickerItem<LeagueKey> => ({
    key,
    icon: <LeagueIcon league={key} />,
    title: leagueName(key),
    subtitle: t('teamEdit.leagueTeamsCount', { count: leagueTeams.count(key), max: leagueTeams.max }),
    disabled: leagueTeams.isFull(key),
  })
  const shown = (key: LeagueKey) => !team.leagues.includes(key) && matches(q, leagueName(key))
  const groups = [
    { label: t('teams.newLeagues'), items: newLeagues(draft).map((l) => l.uid).filter(shown).map(item) },
    { label: t('teams.originalLeagues'), items: originals.map((l) => l.id).filter(shown).map(item) },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('teamEdit.leagues')}</CardTitle>
        <CardDescription>{t('teamEdit.leagueHint')}</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            <Plus /> {t('teamEdit.addLeague')}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <FieldIssues issues={issues} />
        {team.leagues.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('teamEdit.noLeagues')}</p>
        ) : (
          <Table>
            <TableBody>
              {team.leagues.map((key) => (
                <TableRow key={String(key)}>
                  <TableCell className="w-12">
                    <LeagueIcon league={key} />
                  </TableCell>
                  <TableCell>
                    <Link to={leaguePath(key)} state={from.state} className="font-medium underline-offset-4 hover:underline">
                      {leagueName(key)}
                    </Link>
                  </TableCell>
                  <TableCell className="w-12">
                    <Button variant="ghost" size="icon" title={t('teamEdit.leaveLeague')} onClick={() => setLeaving(key)}>
                      <X />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <PickerDialog
        open={adding}
        onOpenChange={setAdding}
        title={t('teamEdit.addLeagueTitle')}
        description={t('teamEdit.addLeagueDescription')}
        placeholder={t('leagues.search')}
        query={q}
        onQuery={setQ}
        groups={groups}
        empty={t('teamEdit.noLeaguesFound')}
        onPick={(key) => updateTeam(team.uid, { leagues: [...team.leagues, key] })}
      />
      <AlertDialog open={leaving !== undefined} onOpenChange={(o) => !o && setLeaving(undefined)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('teamEdit.leaveLeagueTitle', { league: leaving !== undefined ? leagueName(leaving) : '' })}</AlertDialogTitle>
            <AlertDialogDescription>{t('teamEdit.leaveLeagueDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => leaving !== undefined && updateTeam(team.uid, { leagues: team.leagues.filter((l) => l !== leaving) })}
            >
              {t('teamEdit.leaveLeague')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
