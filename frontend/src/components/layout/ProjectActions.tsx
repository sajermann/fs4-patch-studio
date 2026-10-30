import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, CircleAlert, Download, FileArchive, Hammer, Loader2, RotateCcw, Save, Trash2, Undo2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { Issue, Project } from '@/api/types'
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { BuildProgressDialog } from '@/components/layout/BuildProgress'
import { useI18n, type TFunction } from '@/i18n'
import { issueText } from '@/lib/issues'
import { leagueKey, leaguePath, playerPath, playerRef, teamKey, teamPath } from '@/lib/players'
import { useProject } from '@/state/project'
import { useStatus } from '@/state/queries'

function entityLink(t: TFunction, project: Project, uid: string | null) {
  if (!uid) return null
  const unnamed = t('common.unnamed')
  const league = project.leagues.find((l) => l.uid === uid)
  if (league) return { label: t('issues.linkLeague', { name: league.name || unnamed }), to: leaguePath(leagueKey(league)) }
  const team = project.teams.find((tm) => tm.uid === uid)
  if (team) return { label: t('issues.linkTeam', { name: team.name || unnamed }), to: teamPath(teamKey(team)) }
  const player = project.players.find((p) => p.uid === uid)
  if (player)
    return {
      label: t('issues.linkPlayer', { name: `${player.first_name} ${player.last_name}`.trim() || unnamed }),
      to: playerPath(playerRef(player)),
    }
  return null
}

function IssuesDialog({ open, onOpenChange, issues }: { open: boolean; onOpenChange: (v: boolean) => void; issues: Issue[] }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const sorted = [...issues].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1))
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('issues.title')}</DialogTitle>
          <DialogDescription>{t('issues.description')}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh] pr-3">
          {sorted.length === 0 && <p className="text-sm text-muted-foreground">{t('issues.none')}</p>}
          <ul className="space-y-2">
            {sorted.map((i, k) => {
              const link = entityLink(t, draft, i.entity)
              return (
                <li key={k} className="flex items-start gap-2 text-sm">
                  {i.severity === 'error' ? (
                    <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
                  ) : (
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                  )}
                  <div>
                    {link && (
                      <Link to={link.to} className="font-medium underline-offset-4 hover:underline" onClick={() => onOpenChange(false)}>
                        {link.label}
                      </Link>
                    )}
                    <p className="text-muted-foreground">{issueText(t, i)}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

export function ProjectActions() {
  const { t } = useI18n()
  const { dirty, issues, saving, save, discard } = useProject()
  const status = useStatus().data
  const queryClient = useQueryClient()
  const [building, setBuilding] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [issuesOpen, setIssuesOpen] = useState(false)
  const [installOpen, setInstallOpen] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [rebuildOpen, setRebuildOpen] = useState(false)
  const [uninstallOpen, setUninstallOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [deleteSaveOpen, setDeleteSaveOpen] = useState(false)

  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  const patch = status?.patch

  const doSave = async () => {
    try {
      await save()
      toast.success(t('project.saved'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('common.saveFailed'))
    }
  }

  // Ctrl+S saves
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (dirty && !saving) void doSave()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })

  // a patch already up to date is built again only if the user confirms
  const build = () => {
    if (!dirty && patch?.up_to_date) setRebuildOpen(true)
    else void doBuild()
  }

  const doBuild = async () => {
    setRebuildOpen(false)
    setBuilding(true)
    try {
      if (dirty) await save()
      const r = await api.buildPatch()
      await queryClient.invalidateQueries({ queryKey: ['project'] })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
      toast.success(t('patch.built', { count: r.patch.files?.length ?? 0 }))
    } catch (e) {
      if (e instanceof ApiError && e.issues) setIssuesOpen(true)
      toast.error(e instanceof ApiError ? e.message : t('patch.buildFailed'))
    } finally {
      setBuilding(false)
    }
  }

  const install = async () => {
    setInstalling(true)
    try {
      const r = await api.installPatch()
      toast.success(t('patch.installed'), {
        description: t('patch.installedDetail', { count: r.installed.length }),
        duration: 10000,
      })
      setInstallOpen(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('patch.installFailed'))
    } finally {
      setInstalling(false)
      await queryClient.invalidateQueries({ queryKey: ['status'] })
    }
  }

  const uninstall = async () => {
    setInstalling(true)
    try {
      const r = await api.uninstallPatch()
      toast.success(t('patch.uninstalled'), {
        description: t('patch.uninstalledDetail', { restored: r.restored.length, removed: r.removed.length }),
        duration: 10000,
      })
      setUninstallOpen(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('patch.uninstallFailed'))
    } finally {
      setInstalling(false)
      await queryClient.invalidateQueries({ queryKey: ['status'] })
    }
  }

  const deleteSave = async () => {
    setInstalling(true)
    try {
      const r = await api.deleteSave()
      toast.success(r.removed ? t('save.deleted') : t('save.noneToDelete'))
      setDeleteSaveOpen(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('save.deleteFailed'))
    } finally {
      setInstalling(false)
    }
  }

  const exportZip = async () => {
    setExporting(true)
    try {
      const r = await api.exportPatch()
      if (r.path) toast.success(t('patch.exported'), { description: r.path, duration: 10000 })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('patch.exportFailed'))
    } finally {
      setExporting(false)
    }
  }

  const patchBadge = dirty ? (
    <Badge variant="outline">{t('patch.badgeUnsaved')}</Badge>
  ) : !patch?.built ? (
    <Badge variant="outline">{t('patch.badgeNeverBuilt')}</Badge>
  ) : patch.up_to_date ? (
    <Badge variant="secondary">{t('patch.badgeUpToDate')}</Badge>
  ) : (
    <Badge variant="outline" className="border-amber-500 text-amber-700 dark:text-amber-400">
      {t('patch.badgeNotBuilt')}
    </Badge>
  )

  const canInstall = !dirty && !!patch?.up_to_date
  const installed = !!status?.setup.game.installed

  return (
    <div className="flex flex-wrap items-center gap-2">
      {patchBadge}
      <Button variant="ghost" size="sm" onClick={() => setIssuesOpen(true)}>
        <CircleAlert className={errors ? 'text-destructive' : 'text-muted-foreground'} /> {errors}
        <AlertTriangle className={warnings ? 'text-amber-600' : 'text-muted-foreground'} /> {warnings}
      </Button>
      {dirty && (
        <Button variant="ghost" size="sm" onClick={() => setDiscardOpen(true)}>
          <Undo2 /> {t('common.discard')}
        </Button>
      )}
      <Button variant="outline" size="sm" onClick={doSave} disabled={!dirty || saving}>
        {saving ? <Loader2 className="animate-spin" /> : <Save />} {t('common.save')}
      </Button>
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button size="sm" onClick={build} disabled={building || errors > 0}>
              {building ? <Loader2 className="animate-spin" /> : <Hammer />} {t('patch.build')}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{errors > 0 ? t('patch.fixErrorsFirst') : t('patch.buildHint')}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button variant="outline" size="sm" onClick={() => setInstallOpen(true)} disabled={!canInstall}>
              <Download /> {t('patch.install')}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{canInstall ? t('patch.installHint') : t('patch.buildBeforeInstall')}</TooltipContent>
      </Tooltip>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon-sm" aria-label={t('patch.moreActions')} disabled={installing || exporting}>
            {exporting ? <Loader2 className="animate-spin" /> : <ChevronDown />}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuItem disabled={!canInstall} onSelect={() => void exportZip()}>
            <FileArchive /> {t('patch.exportZip')}
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!installed} onSelect={() => setUninstallOpen(true)}>
            <RotateCcw /> {t('patch.uninstallMenu')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" disabled={!status?.config.save_dir} onSelect={() => setDeleteSaveOpen(true)}>
            <Trash2 /> {t('save.deleteMenu')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <IssuesDialog open={issuesOpen} onOpenChange={setIssuesOpen} issues={issues} />
      <BuildProgressDialog open={building} />

      <AlertDialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('project.discardTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('project.discardDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={discard}>{t('common.discard')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={rebuildOpen} onOpenChange={setRebuildOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('patch.rebuildTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('patch.rebuildDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void doBuild()}>{t('patch.rebuild')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={installOpen} onOpenChange={setInstallOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('patch.installTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('patch.installCopiedTo')}{' '}
              <span className="font-mono break-all">{status?.config.game_dir ?? t('patch.gameDirNotSet')}</span>
              {t('patch.installRestoreRest')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <p className="flex items-start gap-2 rounded-md border border-amber-500/50 p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
            {t('patch.installSaveWarning')}
          </p>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={installing}>{t('common.cancel')}</AlertDialogCancel>
            <Button onClick={install} disabled={installing}>
              {installing && <Loader2 className="animate-spin" />} {t('patch.installButton')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteSaveOpen} onOpenChange={setDeleteSaveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('save.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('save.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={installing}>{t('common.cancel')}</AlertDialogCancel>
            <Button variant="destructive" onClick={deleteSave} disabled={installing}>
              {installing && <Loader2 className="animate-spin" />} {t('save.deleteButton')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={uninstallOpen} onOpenChange={setUninstallOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('patch.uninstallTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('patch.uninstallDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <p className="flex items-start gap-2 rounded-md border border-amber-500/50 p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
            {t('patch.uninstallSaveWarning')}
          </p>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={installing}>{t('common.cancel')}</AlertDialogCancel>
            <Button onClick={uninstall} disabled={installing}>
              {installing && <Loader2 className="animate-spin" />} {t('patch.uninstallButton')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
