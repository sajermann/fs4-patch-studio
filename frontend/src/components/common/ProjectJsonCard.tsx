import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, Pencil, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from '@/lib/notify'
import { ApiError, BACKUP_FILE_URL, api } from '@/api/client'
import type { BackupProgress as Progress, Project } from '@/api/types'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { BackupProgress } from '@/components/common/BackupProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { translate, useI18n } from '@/i18n'
import { useProject } from '@/state/project'

/** Message for a project the backend refused (422 without a code: not the shape of a project). */
const refusal = (e: unknown) =>
  e instanceof ApiError
    ? e.status === 422 && !e.code
      ? translate('projectJson.badShape')
      : e.message
    : translate('projectJson.saveFailed')

const POLL_MS = 400
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** Saves the finished backup zip through the browser's (or the desktop app's) download. */
function downloadBackup() {
  const link = document.createElement('a')
  link.href = BACKUP_FILE_URL
  link.download = ''
  document.body.appendChild(link)
  link.click()
  link.remove()
}

/** The saved project as JSON (the app's database): view and edit in place; backup = zip of the project folder
 * (database.json + images + faces), downloaded or restored. Editing or restoring replaces the saved project, so both
 * ask first; unsaved changes in the editor must be saved or discarded before. */
export function ProjectJsonCard() {
  const { t } = useI18n()
  const { dirty } = useProject()
  const queryClient = useQueryClient()
  const saved = useQuery({ queryKey: ['project'], queryFn: api.project, staleTime: Infinity }).data?.project
  const text = saved ? JSON.stringify(saved, null, 2) : ''
  const [confirm, setConfirm] = useState<null | 'edit' | { backup: File }>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // the backup download or restore running now, with its progress (shown under the buttons / in the dialog)
  const [run, setRun] = useState<{ action: 'export' | 'restore'; prog?: Progress } | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const replace = async (project: Project, done: string) => {
    setBusy(true)
    try {
      await api.saveProject(project)
      await queryClient.invalidateQueries({ queryKey: ['project'] })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
      toast.success(done)
      return true
    } catch (e) {
      toast.error(refusal(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  const parse = (raw: string): Project | null => {
    try {
      const value = JSON.parse(raw)
      if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error()
      return value as Project
    } catch {
      toast.error(t('projectJson.invalid'))
      return null
    }
  }

  const saveEdit = async () => {
    const project = editing !== null && parse(editing)
    if (project && (await replace(project, t('projectJson.saved')))) setEditing(null)
  }

  /** The zip is written in the background (it can take a while on a big project): follow it, then download it. */
  const backup = async () => {
    setRun({ action: 'export' })
    try {
      await api.startBackup()
      let prog: Progress
      do {
        await sleep(POLL_MS)
        prog = await api.backupProgress()
        setRun({ action: 'export', prog })
      } while (prog.running)
      if (prog.error) throw new ApiError(500, prog.error)
      downloadBackup()
      toast.success(t('projectJson.backupReady'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('backup.failed'))
    } finally {
      setRun(null)
    }
  }

  /** Upload measured here; once the file is sent, the backend's steps (checking, extracting, opening). The clock
   * counts from the click. */
  const restore = async (file: File) => {
    setBusy(true)
    const started = Date.now()
    const elapsed = () => (Date.now() - started) / 1000
    let sent = false
    const uploading = (done: number, total: number): Progress => ({
      running: true, phase: 'uploading', done: 0, total: 0, bytes_done: done, bytes_total: total, elapsed: elapsed(),
    })
    setRun({ action: 'restore', prog: uploading(0, file.size) })
    const timer = setInterval(() => {
      if (!sent) return
      api
        .backupProgress()
        .then((prog) => prog.action === 'restore' && prog.running && setRun({ action: 'restore', prog: { ...prog, elapsed: elapsed() } }))
        .catch(() => {})
    }, POLL_MS)
    try {
      await api.restoreBackup(file, (done, total) => {
        sent = done >= total
        setRun({ action: 'restore', prog: sent ? { ...uploading(done, total), phase: 'checking', bytes_done: 0, bytes_total: 0 } : uploading(done, total) })
      })
      await queryClient.invalidateQueries({ queryKey: ['project'] })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
      toast.success(t('projectJson.restored'))
      return true
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('projectJson.restoreFailed'))
      return false
    } finally {
      clearInterval(timer)
      setRun(null)
      setBusy(false)
    }
  }

  const pickFile = (file: File | undefined) => {
    if (fileInput.current) fileInput.current.value = ''
    if (file) setConfirm({ backup: file })
  }

  const blocked = dirty ? t('projectJson.saveOrDiscardFirst') : undefined

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('projectJson.title')}</CardTitle>
        <CardDescription>{t('projectJson.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {editing === null ? (
          <pre className="max-h-96 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs">{text || t('projectJson.empty')}</pre>
        ) : (
          <Textarea
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
            spellCheck={false}
            className="h-96 font-mono text-xs"
          />
        )}
        <div className="flex flex-wrap gap-2">
          {editing === null ? (
            <>
              <Button variant="outline" onClick={() => setConfirm('edit')} disabled={!!blocked || !saved} title={blocked}>
                <Pencil /> {t('projectJson.edit')}
              </Button>
              <Button variant="outline" onClick={() => void backup()} disabled={!!run}>
                {run?.action === 'export' ? <Loader2 className="animate-spin" /> : <Download />} {t('projectJson.backup')}
              </Button>
              <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={!!blocked || !!run} title={blocked}>
                <Upload /> {t('projectJson.importBackup')}
              </Button>
              <input
                ref={fileInput}
                type="file"
                accept=".zip,application/zip"
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0])}
              />
            </>
          ) : (
            <>
              <Button onClick={() => void saveEdit()} disabled={busy}>
                {busy && <Loader2 className="animate-spin" />} {t('projectJson.saveJson')}
              </Button>
              <Button variant="ghost" onClick={() => setEditing(null)} disabled={busy}>
                {t('common.cancel')}
              </Button>
            </>
          )}
        </div>
        {run?.action === 'export' && <BackupProgress action="export" prog={run.prog} />}
      </CardContent>

      <AlertDialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent width="md">
          <AlertDialogHeader>
            <AlertDialogTitle>{confirm === 'edit' ? t('projectJson.editTitle') : t('projectJson.importTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === 'edit'
                ? t('projectJson.editWarning')
                : t('projectJson.importWarning', { name: confirm?.backup.name ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {run?.action === 'restore' && <BackupProgress action="restore" prog={run.prog} />}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={async () => {
                if (confirm === 'edit') {
                  setEditing(text)
                  setConfirm(null)
                } else if (confirm && (await restore(confirm.backup))) {
                  setConfirm(null)
                }
              }}
            >
              {busy && <Loader2 className="animate-spin" />} {confirm === 'edit' ? t('projectJson.editAnyway') : t('projectJson.import')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
