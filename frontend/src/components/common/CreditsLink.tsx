import { ExternalLink } from 'lucide-react'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

/** Only http(s) addresses become links (the backend already keeps nothing else; this guards older data). */
const webLink = (url?: string | null) => (url && /^https?:\/\//i.test(url) ? url : null)

const hostOf = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** Who made something (credits), as a link to their page when there is one; the link opens in the browser and its
 * click does not reach the row or card around it. Without credits nor link: nothing (or `empty`). */
export function CreditsLink({
  credits,
  url,
  className,
  empty = null,
}: {
  credits?: string | null
  url?: string | null
  className?: string
  empty?: React.ReactNode
}) {
  const { t } = useI18n()
  const href = webLink(url)
  const text = credits?.trim() || (href ? hostOf(href) : '')
  if (!text) return <>{empty}</>
  if (!href) return <span className={className}>{text}</span>
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      title={t('credits.openLink', { url: href })}
      onClick={(e) => e.stopPropagation()}
      className={cn('inline-flex min-w-0 items-center gap-0.5 underline-offset-2 hover:text-foreground hover:underline', className)}
    >
      <span className="truncate">{text}</span>
      <ExternalLink className="size-3 shrink-0" />
    </a>
  )
}
