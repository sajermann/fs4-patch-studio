import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, CircleAlert, FolderOpen, LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from '@/lib/notify'
import { ApiError, api } from '@/api/client'
import { PackProblems } from '@/components/common/FacePicker'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { rich } from '@/i18n/rich'

const CHECK_DELAY_MS = 500

/** Layout of a pack folder (fsmod.scanface.FILES; <id> = the face id the manifest uses). */
const FOLDER_EXAMPLE = `my-pack/
├─ manifest.json
├─ faces/
│  └─ face_<id>_0_0_0_0_0_0_0_0_textures.rx3
├─ heads/
│  ├─ head_<id>_0.rx3
│  └─ eyes_<id>_0_textures.rx3
├─ hair/
│  ├─ hair_<id>_0_0.rx3
│  └─ hair_<id>_0_textures.rx3
└─ hairlod/
   └─ hairlod_<id>_0_0.rx3`

/** Example shown under "How to make the manifest.json" (the format fsmod.facepack.read_manifest reads). */
const MANIFEST_EXAMPLE = `{
  "type": "fs4-faces",
  "version": 1,
  "credits": "Colgado",
  "credits_url": "https://www.soccergaming.com",
  "faces": [
    { "id": 51318, "name": "Luis Brahim Palma" },
    { "id": 51371, "name": "Michael Alexander", "credits": "Other author", "credits_url": "https://example.com" }
  ]
}`

/** The face pack folders of the settings: one row per folder (typed or picked), each with what the backend found in
 * it (number of faces, folder without faces, problems of its manifest.json). Empty rows are dropped on save. */
export function FacePackFolders({ value, onChange }: { value: string[]; onChange: (folders: string[]) => void }) {
  const { t } = useI18n()
  const rows = value.length ? value : ['']
  const set = (i: number, folder: string) => onChange(rows.map((f, k) => (k === i ? folder : f)))
  const remove = (i: number) => onChange(rows.filter((_, k) => k !== i))

  const folders = rows.map((f) => f.trim()).filter(Boolean)
  const [checked, setChecked] = useState(folders) // checked after the user stops typing
  const key = JSON.stringify(folders)
  useEffect(() => {
    const timer = setTimeout(() => setChecked(JSON.parse(key) as string[]), CHECK_DELAY_MS)
    return () => clearTimeout(timer)
  }, [key])
  const check = useQuery({
    queryKey: ['facepack-check', checked],
    queryFn: () => api.facePacks(checked),
    enabled: checked.length > 0,
    retry: false,
  })
  /** What was found in one folder: its packs (several when it brings versions side by side), summed up. */
  const statusOf = (folder: string) => {
    const index = checked.indexOf(folder.trim())
    const parts = check.data?.packs.filter((p) => p.index === index) ?? []
    if (!parts.length) return undefined
    return {
      error: parts.find((p) => p.error)?.error ?? null,
      name: parts.length > 1 ? t('settings.facePackParts', { name: parts[0].name.split(' / ')[0], count: parts.length }) : parts[0].name,
      count: parts.reduce((n, p) => n + p.count, 0),
    }
  }

  const browse = async (i: number) => {
    try {
      const { folder } = await api.browseFolder(rows[i] || [...rows].reverse().find((f) => f.trim()) || null)
      if (folder) set(i, folder)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('folder.dialogFailed'))
    }
  }

  return (
    <div className="space-y-2">
      {rows.map((folder, i) => {
        const status = folder.trim() && checked.includes(folder.trim()) ? statusOf(folder) : undefined
        return (
          <div key={i} className="space-y-1">
            <div className="flex gap-1">
              <Input value={folder} onChange={(e) => set(i, e.target.value)} placeholder={t('settings.facePackPlaceholder')} className="font-mono" />
              <Button variant="outline" onClick={() => void browse(i)} title={t('folder.browseHint')}>
                <FolderOpen /> {t('common.browse')}
              </Button>
              <Button variant="ghost" size="icon" onClick={() => remove(i)} title={t('settings.facePackRemove')} aria-label={t('settings.facePackRemove')}>
                <Trash2 />
              </Button>
            </div>
            {folder.trim() &&
              (status ? (
                <p className={`flex items-center gap-1 text-xs ${status.error ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {status.error ? <CircleAlert className="size-3.5" /> : <CheckCircle2 className="size-3.5 text-emerald-600" />}
                  {status.error ? t('settings.facePackNoFaces') : t('settings.facePackStatus', { name: status.name, count: status.count })}
                </p>
              ) : (
                check.isFetching && <LoaderCircle className="size-3.5 animate-spin text-muted-foreground" />
              ))}
          </div>
        )
      })}
      <Button variant="outline" size="sm" onClick={() => onChange([...rows, ''])}>
        <Plus /> {t('settings.facePackAdd')}
      </Button>
      {check.data && <PackProblems packs={check.data.packs.filter((p) => !p.error)} />}
      <details className="rounded-md border px-3 py-2 text-xs">
        <summary className="cursor-pointer font-medium">{t('settings.manifestHelp')}</summary>
        <p className="mt-2 font-medium">{t('settings.folderLayoutTitle')}</p>
        <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 font-mono text-[11px]">{FOLDER_EXAMPLE}</pre>
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-muted-foreground">
          <li>{rich(t('settings.folderLayoutFaces'))}</li>
          <li>{rich(t('settings.folderLayoutHeads'))}</li>
          <li>{rich(t('settings.folderLayoutHair'))}</li>
          <li>{rich(t('settings.folderLayoutHairlod'))}</li>
          <li>{rich(t('settings.folderLayoutScreenassets'))}</li>
          <li>{rich(t('settings.folderLayoutVersions'))}</li>
        </ul>
        <p className="mt-3 font-medium">{t('settings.manifestTitle')}</p>
        <p className="mt-1 text-muted-foreground">{t('settings.manifestHelpText')}</p>
        <pre className="mt-2 overflow-x-auto rounded bg-muted p-2 font-mono text-[11px]">{MANIFEST_EXAMPLE}</pre>
      </details>
    </div>
  )
}
