import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, Pencil, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { Project } from '@/api/types'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
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

  const restore = async (file: File) => {
    setBusy(true)
    try {
      await api.restoreBackup(file)
      await queryClient.invalidateQueries({ queryKey: ['project'] })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
      toast.success(t('projectJson.restored'))
      return true
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('projectJson.restoreFailed'))
      return false
    } finally {
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
              <Button variant="outline" asChild>
                <a href="/api/project/backup" download>
                  <Download /> {t('projectJson.backup')}
                </a>
              </Button>
              <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={!!blocked} title={blocked}>
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
      </CardContent>

      <AlertDialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirm === 'edit' ? t('projectJson.editTitle') : t('projectJson.importTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === 'edit'
                ? t('projectJson.editWarning')
                : t('projectJson.importWarning', { name: confirm?.backup.name ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
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
