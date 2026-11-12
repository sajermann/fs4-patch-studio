import { Bell, Check, CheckCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { AppNotification } from '@/api/types'
import { useDateText } from '@/components/common/dates'
import { KindIcon, NotificationDialog, useNotificationActions } from '@/components/common/notifications'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useI18n } from '@/i18n'
import { useUnreadNotifications } from '@/state/queries'

/** Header bell: unread count, the 5 newest unread ones (title + one line of the description; click = the whole
 * notification in a dialog), "mark read" per item and for all, and the link to the notifications page. Opening the
 * bell marks nothing read. */
export function NotificationBell() {
  const { t } = useI18n()
  const date = useDateText()
  const { data, error } = useUnreadNotifications()
  const actions = useNotificationActions()
  const [open, setOpen] = useState(false)
  const [shown, setShown] = useState<AppNotification | null>(null)
  const unread = data?.unread ?? 0

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon-sm" className="relative" aria-label={t('notifications.bell', { count: unread })} title={t('notifications.title')}>
            <Bell />
            {unread > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-none font-semibold text-white tabular-nums">
                {unread > 99 ? '99+' : unread}
              </span>
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-96 p-0">
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <p className="text-sm font-medium">
              {t('notifications.title')}
              {unread > 0 && <span className="ml-2 text-xs font-normal text-muted-foreground">{t('notifications.unreadCount', { count: unread })}</span>}
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={!unread || actions.busy}
              onClick={() => void actions.mark({ all: true, state: 'unread' })}
            >
              <CheckCheck /> {t('notifications.markAllRead')}
            </Button>
          </div>
          <DropdownMenuSeparator className="my-0" />
          {error ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t('notifications.loadFailed')}</p>
          ) : !data?.items.length ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t('notifications.noUnread')}</p>
          ) : (
            <ul className="py-1">
              {data.items.map((n) => (
                <li key={n.id} className="flex items-center gap-1 px-1 py-0.5">
                  {/* the notification (opens the dialog) and "mark read" are separate targets, each with its own hover */}
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent"
                    onClick={() => {
                      setOpen(false)
                      setShown(n)
                    }}
                  >
                    <KindIcon kind={n.kind} className="mt-0.5" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{n.title}</span>
                      {n.description && <span className="block truncate text-xs text-muted-foreground">{n.description}</span>}
                      <span className="block text-[11px] text-muted-foreground tabular-nums">{date(n.created_at)}</span>
                    </span>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="shrink-0"
                    disabled={actions.busy}
                    title={t('notifications.markRead')}
                    aria-label={t('notifications.markRead')}
                    onClick={() => void actions.mark({ ids: [n.id] })}
                  >
                    <Check />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <DropdownMenuSeparator className="my-0" />
          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-center text-sm font-medium underline-offset-4 hover:underline"
          >
            {t('notifications.seeAll')}
          </Link>
        </DropdownMenuContent>
      </DropdownMenu>
      <NotificationDialog notification={shown} onClose={() => setShown(null)} />
    </>
  )
}
