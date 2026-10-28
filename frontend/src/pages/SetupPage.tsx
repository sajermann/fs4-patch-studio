import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, CircleAlert, FolderOpen, Loader2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { GameCheck, Status } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PreferencesMenu } from '@/components/layout/PreferencesMenu'
import { useI18n } from '@/i18n'
import { rich } from '@/i18n/rich'
import { APP_VERSION } from '@/lib/about'

/** Folder field with a "browse" button (Windows folder picker opened by the backend). */
function FolderInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const { t } = useI18n()
  const browse = async () => {
    try {
      const { folder } = await api.browseFolder(value || null)
      if (folder) onChange(folder)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('folder.dialogFailed'))
    }
  }
  return (
    <div className="flex gap-1">
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="font-mono" />
      <Button variant="outline" onClick={() => void browse()} title={t('folder.browseHint')}>
        <FolderOpen /> {t('common.browse')}
      </Button>
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">
        <span className="mr-2 inline-flex size-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
          {n}
        </span>
        {title}
      </p>
      {children}
    </div>
  )
}

/** What the check of the game folder found. */
function GameCheckResult({ check, originalsOk }: { check: GameCheck; originalsOk: boolean }) {
  const { t } = useI18n()
  if (!check.valid)
    return (
      <p className="flex items-center gap-2 text-sm text-destructive">
        <CircleAlert className="size-4" /> {t('setup.notRestreet')}
      </p>
    )
  const bad = Object.entries(check.files).filter(([, s]) => s !== 'ok')
  return (
    <div className="space-y-1 text-sm">
      {check.tested ? (
        <p className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="size-4" /> ReStreet {check.version}
        </p>
      ) : (
        <p className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
          <AlertTriangle className="size-4" /> ReStreet {check.version ?? t('shell.unknownVersion')}: {t('setup.untested')}
        </p>
      )}
      {check.official ? (
        <p className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="size-4" />
          {originalsOk ? t('setup.filesOk') : t('setup.filesOkWillCopy')}
        </p>
      ) : check.app_patch && originalsOk ? (
        <p className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="size-4" /> {t('setup.hasAppPatch')}
        </p>
      ) : (
        <div className="text-destructive">
          <p className="flex items-start gap-2">
            <CircleAlert className="mt-0.5 size-4 shrink-0" />
            {check.app_patch ? t('setup.appPatchNoOriginals') : t('setup.notOfficial')}
          </p>
          <ul className="mt-1 ml-6 font-mono text-xs">
            {bad.map(([f, s]) => (
              <li key={f}>
                {f}: {s === 'missing' ? t('setup.fileMissing') : s === 'added' ? t('setup.fileAdded') : t('setup.fileModified')}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** First-run setup: game folder (checked), save folder, optional face pack, and the notice
 * that must be accepted before going on. Also reachable from the settings to change the folders. */
export function SetupPage({ status }: { status: Status }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const cfg = status.config
  const [gameDir, setGameDir] = useState(cfg.game_dir ?? '')
  const [saveDir, setSaveDir] = useState(cfg.save_dir ?? '')
  const [facePackDir, setFacePackDir] = useState(cfg.face_pack_dir ?? '')
  const [check, setCheck] = useState<GameCheck | null>(null)
  const [checking, setChecking] = useState(false)
  const [accepted, setAccepted] = useState(cfg.terms_version === status.setup.terms_version)
  const [applying, setApplying] = useState(false)
  const originalsOk = check?.originals.verified ?? status.setup.originals.verified
  const firstRun = status.setup.required

  const runCheck = async (dir = gameDir) => {
    if (!dir.trim()) return
    setChecking(true)
    setCheck(null)
    try {
      const result = await api.setupCheck(dir.trim())
      setCheck(result)
      if (!saveDir && result.save_dir_guess) setSaveDir(result.save_dir_guess)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('setup.checkFailed'))
    } finally {
      setChecking(false)
    }
  }

  // official files, or the app's own patch (only when the app already has the originals to undo it)
  const gameOk = !!check?.valid && (check.official || (check.app_patch && originalsOk))
  const canGo = gameOk && !!saveDir.trim() && accepted && !applying

  const apply = async () => {
    setApplying(true)
    try {
      const r = await api.setupApply({
        game_dir: gameDir.trim(),
        save_dir: saveDir.trim(),
        face_pack_dir: facePackDir.trim() || null,
        terms_version: status.setup.terms_version,
      })
      if (r.imported.length) toast.success(t('setup.imported', { count: r.imported.length }))
      await queryClient.invalidateQueries()
      navigate('/teams')
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('setup.saveFailed'))
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{firstRun ? t('setup.titleFirstRun') : t('setup.title')}</h1>
          <p className="text-muted-foreground">{firstRun ? t('setup.descriptionFirstRun') : t('setup.description')}</p>
        </div>
        <PreferencesMenu />
      </div>
      <Card>
        <CardContent className="space-y-6 pt-6">
          <Step n={1} title={t('setup.step1')}>
            <FolderInput
              value={gameDir}
              onChange={(v) => {
                setGameDir(v)
                setCheck(null)
              }}
              placeholder={t('setup.gameDirPlaceholder')}
            />
            <div className="flex items-center gap-3">
              <Button variant="secondary" onClick={() => void runCheck()} disabled={checking || !gameDir.trim()}>
                {checking && <Loader2 className="animate-spin" />} {t('setup.check')}
              </Button>
              {checking && <span className="text-sm text-muted-foreground">{t('setup.checking')}</span>}
            </div>
            {check && <GameCheckResult check={check} originalsOk={originalsOk} />}
          </Step>
          <Step n={2} title={t('settings.saveDir')}>
            <FolderInput value={saveDir} onChange={setSaveDir} placeholder={t('setup.saveDirPlaceholder')} />
            <p className="text-xs text-muted-foreground">{t('setup.saveDirHint')}</p>
          </Step>
          <Step n={3} title={t('settings.facePackDir')}>
            <FolderInput value={facePackDir} onChange={setFacePackDir} placeholder={t('settings.facePackPlaceholder')} />
            <p className="text-xs text-muted-foreground">{t('setup.facePackHint')}</p>
          </Step>
        </CardContent>
      </Card>

      <Card className="border-amber-500/50">
        <CardHeader>
          <CardTitle>{t('setup.noticeTitle')}</CardTitle>
          <CardDescription>{t('setup.noticeDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <ul className="list-disc space-y-2 pl-5">
            <li>{rich(t('setup.notice1'))}</li>
            <li>{t('setup.notice2')}</li>
            <li>{rich(t('setup.notice3'))}</li>
            <li>{t('setup.notice4')}</li>
          </ul>
          <div className="flex items-start gap-2">
            <Checkbox id="accept" checked={accepted} onCheckedChange={(v) => setAccepted(v === true)} />
            <Label htmlFor="accept" className="leading-snug">
              {t('setup.accept')}
            </Label>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        <span className="mr-auto text-xs text-muted-foreground">
          {t('app.version')} {APP_VERSION}
        </span>
        {applying && !originalsOk && <span className="text-sm text-muted-foreground">{t('setup.copying')}</span>}
        {!firstRun && (
          <Button variant="ghost" onClick={() => navigate('/settings')} disabled={applying}>
            {t('common.cancel')}
          </Button>
        )}
        <Button onClick={() => void apply()} disabled={!canGo} title={canGo ? undefined : t('setup.cannotGo')}>
          {applying && <Loader2 className="animate-spin" />} {t('setup.next')}
        </Button>
      </div>
    </div>
  )
}
