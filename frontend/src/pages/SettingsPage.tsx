import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, CircleAlert, FolderOpen, Loader2, Settings2, Trash2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { Config, Status } from '@/api/types'
import { Field } from '@/components/common/form'
import { PlayersBaseCard } from '@/components/common/PlayersBaseCard'
import { ProjectJsonCard } from '@/components/common/ProjectJsonCard'
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
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { rich } from '@/i18n/rich'
import { useStatus } from '@/state/queries'

function Line({ ok, warn, children }: { ok: boolean; warn?: boolean; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
      ) : warn ? (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
      ) : (
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
      )}
      <span>{children}</span>
    </li>
  )
}

/** The game: folders, ReStreet version, the app's originals and what is installed. */
function GameCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { game, originals } = status.setup
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.gameTitle')}</CardTitle>
        <CardDescription>{t('settings.gameDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted-foreground">{t('settings.gameDir')}</dt>
          <dd className="font-mono break-all">{status.config.game_dir ?? '—'}</dd>
          <dt className="text-muted-foreground">{t('settings.saveDir')}</dt>
          <dd className="font-mono break-all">{status.config.save_dir ?? '—'}</dd>
        </dl>
        <ul className="space-y-1 text-sm">
          <Line ok={game.tested} warn>
            ReStreet {game.version ?? t('shell.unknownVersion')}
            {!game.tested && ` — ${t('settings.untested', { tested: game.tested_versions })}`}
          </Line>
          <Line ok={originals.verified}>
            {originals.verified ? t('settings.originalsOk') : t('settings.originalsBad')}
          </Line>
          <Line ok={game.installed && !game.changed.length} warn>
            {!game.installed
              ? t('settings.notInstalled')
              : game.changed.length
                ? t('settings.installedChanged', { count: game.changed.length })
                : t('settings.installed')}
          </Line>
        </ul>
        <Button variant="outline" onClick={() => navigate('/setup')}>
          <Settings2 /> {t('settings.changeFolders')}
        </Button>
      </CardContent>
    </Card>
  )
}

/** Deleting the save by hand (the install/uninstall do it too). */
function SaveCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const remove = async () => {
    setBusy(true)
    try {
      const r = await api.deleteSave()
      toast.success(r.removed ? t('save.deleted') : t('save.noneToDelete'))
      setOpen(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('save.deleteFailed'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.saveTitle')}</CardTitle>
        <CardDescription>{t('settings.saveDescription')}</CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="destructive" onClick={() => setOpen(true)} disabled={!status.config.save_dir}>
          <Trash2 /> {t('save.deleteButton')}
        </Button>
      </CardContent>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('save.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('save.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => (e.preventDefault(), void remove())} disabled={busy}>
              {busy && <Loader2 className="animate-spin" />} {t('save.deleteButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

export function SettingsPage() {
  const { t } = useI18n()
  const status = useStatus().data
  const queryClient = useQueryClient()
  const [config, setConfig] = useState<Config | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (status && !config) setConfig(status.config)
  }, [status, config])

  if (!status || !config) return <Loader2 className="animate-spin" />

  const set = (patch: Partial<Config>) => setConfig({ ...config, ...patch })
  const browseFaces = async () => {
    try {
      const { folder } = await api.browseFacePack()
      if (folder) set({ face_pack_dir: folder })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('folder.dialogFailed'))
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      const facePackDir = config.face_pack_dir?.trim() || null
      if (facePackDir) {
        try {
          const pack = await api.facePack(facePackDir) // checks the folder before keeping it
          toast.info(t('settings.facePackFound', { count: pack.faces.length }))
        } catch (e) {
          toast.error(e instanceof ApiError ? e.message : t('settings.facePackInvalid'))
          return
        }
      }
      // the game and save folders change only through the setup screen (it checks them)
      await api.saveConfig({
        ...config,
        game_dir: status.config.game_dir,
        save_dir: status.config.save_dir,
        face_pack_dir: facePackDir,
        players_base_file: status.config.players_base_file, // saved by its own card
      })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
      await queryClient.invalidateQueries({ queryKey: ['project'] })
      await queryClient.invalidateQueries({ queryKey: ['facepack'] })
      toast.success(t('settings.saved'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('common.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t('nav.settings')}</h1>
      <GameCard status={status} />
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.foldersTitle')}</CardTitle>
          <CardDescription>{t('settings.foldersDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label={t('settings.projectDir')} hint={t('settings.projectDirHint')}>
            <Input value={config.project_dir} onChange={(e) => set({ project_dir: e.target.value })} className="font-mono" />
          </Field>
          <Field label={t('settings.backupsDir')}>
            <Input value={config.backups_dir} onChange={(e) => set({ backups_dir: e.target.value })} className="font-mono" />
          </Field>
          <Field
            label={t('settings.facePackDir')}
            hint={t('settings.facePackDirHint')}
          >
            <div className="flex gap-1">
              <Input
                value={config.face_pack_dir ?? ''}
                onChange={(e) => set({ face_pack_dir: e.target.value })}
                placeholder={t('settings.facePackPlaceholder')}
                className="font-mono"
              />
              <Button variant="outline" onClick={() => void browseFaces()} title={t('folder.browseHint')}>
                <FolderOpen /> {t('common.browse')}
              </Button>
            </div>
          </Field>
          <Button onClick={save} disabled={saving}>
            {saving && <Loader2 className="animate-spin" />} {t('settings.save')}
          </Button>
        </CardContent>
      </Card>
      <PlayersBaseCard status={status} />
      <SaveCard status={status} />
      <ProjectJsonCard />
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.patchTitle')}</CardTitle>
          <CardDescription>{rich(t('settings.patchDescription', { folder: status.patch.folder }))}</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {status.patch.built ? t('settings.lastPatch', { date: status.patch.built_at }) : t('settings.noPatch')}
        </CardContent>
      </Card>
    </div>
  )
}
