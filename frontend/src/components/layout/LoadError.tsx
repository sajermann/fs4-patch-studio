import { CircleAlert, RotateCw } from 'lucide-react'
import { ApiError } from '@/api/client'
import { SupportActions } from '@/components/common/SupportActions'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

function Code({ children }: { children: string }) {
  return <pre className="whitespace-pre-wrap break-all rounded bg-muted p-2 font-mono text-xs text-foreground">{children}</pre>
}

/** What failed, the file it was about and where the log is, instead of loading forever or a blank page. `page`:
 * centered on the whole window (nothing else could open); otherwise it fits in the page area. */
export function LoadError({
  error,
  onRetry,
  title,
  page = false,
}: {
  error: unknown
  onRetry: () => void
  title: string
  page?: boolean
}) {
  const { t } = useI18n()
  const api = error instanceof ApiError ? error : undefined
  const summary = api?.summary ?? t('app.unexpectedError')
  const detail = api ? api.error : error instanceof Error ? `${error.name}: ${error.message}` : String(error)
  return (
    <div className={cn('flex justify-center', page ? 'min-h-svh items-center p-8' : 'py-8')}>
      <Alert variant="destructive" className="max-w-2xl">
        <CircleAlert />
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>{summary}</p>
          {detail && detail !== summary && <Code>{detail}</Code>}
          {api?.path && !summary.includes(api.path) && <Code>{api.path}</Code>}
          <p>{api?.logFile ? t('app.loadFailedLog') : t('app.loadFailedReport')}</p>
          {api?.logFile && <Code>{api.logFile}</Code>}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RotateCw /> {t('app.retry')}
            </Button>
            {api?.status !== 0 && <SupportActions size="sm" />}
          </div>
        </AlertDescription>
      </Alert>
    </div>
  )
}
