import { ClipboardCopy, FolderOpen, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'

/** Copies text; the textarea fallback covers browsers that refuse the clipboard API. */
async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return
  } catch {
    /* fall back below */
  }
  const area = document.createElement('textarea')
  area.value = text
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  area.remove()
  if (!ok) throw new Error('copy refused')
}

/** "Copy report" and "Open logs folder": what someone asking for help sends. Used in the Settings and on the error
 * screens (which open when the rest of the app cannot). */
export function SupportActions({ size = 'default' }: { size?: 'default' | 'sm' }) {
  const { t } = useI18n()
  const [copying, setCopying] = useState(false)

  const copyReport = async () => {
    setCopying(true)
    try {
      await copyText(await api.logsReport())
      toast.success(t('support.reportCopied'))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('support.reportFailed'))
    } finally {
      setCopying(false)
    }
  }

  const openLogs = async () => {
    try {
      await api.openLogs()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('support.openLogsFailed'))
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" size={size} onClick={() => void copyReport()} disabled={copying}>
        {copying ? <Loader2 className="animate-spin" /> : <ClipboardCopy />} {t('support.copyReport')}
      </Button>
      <Button variant="outline" size={size} onClick={() => void openLogs()}>
        <FolderOpen /> {t('support.openLogs')}
      </Button>
    </div>
  )
}
