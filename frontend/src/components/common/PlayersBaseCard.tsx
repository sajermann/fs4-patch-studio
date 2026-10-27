import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleAlert, FolderOpen, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { Status } from '@/api/types'
import { Field } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { rich } from '@/i18n/rich'

// Same contract as fsapi/ea_players.py: shown to the user so a wrong field name ("player_name") is easy to spot.
// Same fields as fsapi/ea_players.py; "attributes" needs every one listed (the skill bars are converted from them).
const CONTRACT_EXAMPLE = `{
  "players": {
    "277643": {
      "name": "Lamine Yamal",
      "club": "FC Barcelona",
      "nationality": "Spain",
      "first_name": "Lamine",
      "last_name": "Yamal",
      "jersey_name": "Lamine Yamal",
      "birth_date": "2007-07-13",
      "height_cm": 181,
      "weight_kg": 72,
      "preferred_foot": "Left",
      "positions": ["RW", "RM"],
      "skill_moves": 4,
      "attributes": {
        "acceleration": 91, "sprint_speed": 86, "agility": 90, "balance": 84, "reactions": 84,
        "ball_control": 90, "dribbling": 91, "finishing": 80, "shot_power": 80, "long_shots": 78,
        "volleys": 71, "penalties": 70, "positioning": 84, "vision": 89, "crossing": 87,
        "short_passing": 85, "long_passing": 76, "curve": 88, "freekick_accuracy": 70,
        "interceptions": 25, "heading_accuracy": 50, "defensive_awareness": 30,
        "standing_tackle": 30, "sliding_tackle": 27, "jumping": 58, "stamina": 75,
        "strength": 52, "aggression": 45, "gk_diving": 8, "gk_handling": 9,
        "gk_positioning": 8, "gk_reflexes": 10
      }
    }
  }
}`

type CheckResult = { players: number; skipped: number; problems: string[] }

/** Players base (who each EA player id is): a JSON the user makes and points to here. No
 * base ships with the app; without one the face gallery shows only ids. */
export function PlayersBaseCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [file, setFile] = useState(status.config.players_base_file ?? '')
  const [result, setResult] = useState<CheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const check = async (path: string) => {
    setResult(null)
    setError(null)
    try {
      const r = await api.checkPlayersBase(path)
      setResult(r)
      return r
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('playersBase.readFailed'))
      return null
    }
  }

  const browse = async () => {
    try {
      const { file: picked } = await api.browsePlayersBase()
      if (picked) {
        setFile(picked)
        await check(picked)
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('playersBase.dialogFailed'))
    }
  }

  const save = async () => {
    setBusy(true)
    try {
      const path = file.trim() || null
      if (path) {
        const r = await check(path)
        if (!r) return
        if (!r.players) {
          toast.error(t('playersBase.noneValid'))
          return
        }
      }
      await api.saveConfig({ ...status.config, players_base_file: path })
      await queryClient.invalidateQueries({ queryKey: ['status'] })
      await queryClient.invalidateQueries({ queryKey: ['facepack'] })
      toast.success(path ? t('playersBase.saved') : t('playersBase.removed'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('common.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('playersBase.title')}</CardTitle>
        <CardDescription>{t('playersBase.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label={t('playersBase.file')}>
          <div className="flex gap-1">
            <Input value={file} onChange={(e) => setFile(e.target.value)} placeholder={t('playersBase.filePlaceholder')} className="font-mono" />
            <Button variant="outline" onClick={() => void browse()} title={t('playersBase.browseHint')}>
              <FolderOpen /> {t('common.browse')}
            </Button>
          </div>
        </Field>

        {error && (
          <p className="flex items-start gap-2 text-sm text-destructive">
            <CircleAlert className="mt-0.5 size-4 shrink-0" /> {error}
          </p>
        )}
        {result && (
          <div className="space-y-1 text-sm">
            <p className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-emerald-600" /> {t('playersBase.valid', { count: result.players })}
              {result.skipped > 0 && <span className="text-amber-600">· {t('playersBase.skipped', { count: result.skipped })}</span>}
            </p>
            {result.problems.length > 0 && (
              <ul className="ml-6 list-disc text-xs text-muted-foreground">
                {result.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
                {result.skipped > result.problems.length && <li>{t('playersBase.more', { count: result.skipped - result.problems.length })}</li>}
              </ul>
            )}
          </div>
        )}

        <details className="rounded-md border p-3 text-sm">
          <summary className="cursor-pointer font-medium">{t('playersBase.formatTitle')}</summary>
          <div className="mt-2 space-y-2 text-muted-foreground">
            <p>{rich(t('playersBase.formatIntro'))}</p>
            <ul className="ml-5 list-disc">
              <li>{rich(t('playersBase.formatName'))}</li>
              <li>{rich(t('playersBase.formatClub'))}</li>
              <li>{rich(t('playersBase.formatData'))}</li>
              <li>{rich(t('playersBase.formatSkills'))}</li>
            </ul>
            <p>{t('playersBase.formatRules')}</p>
            <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-xs text-foreground">{CONTRACT_EXAMPLE}</pre>
          </div>
        </details>

        <div className="flex gap-2">
          <Button onClick={() => void save()} disabled={busy}>
            {busy && <Loader2 className="animate-spin" />} {t('playersBase.save')}
          </Button>
          <Button variant="outline" onClick={() => void check(file.trim())} disabled={!file.trim() || busy}>
            {t('playersBase.check')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
