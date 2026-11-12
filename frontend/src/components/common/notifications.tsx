import { useQueryClient } from '@tanstack/react-query'
import { CircleCheckIcon, InfoIcon, Loader2, OctagonXIcon, Trash2, TriangleAlertIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '@/api/client'
import type { AppNotification, NotificationKind, NotificationSelection } from '@/api/types'
import { useDateText } from '@/components/common/dates'
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
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'
import { entityLink } from '@/lib/entityLink'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'

const KIND_ICON: Record<NotificationKind, { icon: typeof InfoIcon; className: string }> = {
  error: { icon: OctagonXIcon, className: 'text-destructive' },
  warning: { icon: TriangleAlertIcon, className: 'text-amber-600' },
  success: { icon: CircleCheckIcon, className: 'text-emerald-600 dark:text-emerald-500' },
  info: { icon: InfoIcon, className: 'text-sky-600 dark:text-sky-400' },
}

/** The icon of a notification's kind (the same ones the toasts use). */
export function KindIcon({ kind, className }: { kind: NotificationKind; className?: string }) {
  const { icon: Icon, className: color } = KIND_ICON[kind] ?? KIND_ICON.info
  return <Icon className={cn('size-4 shrink-0', color, className)} />
}

/** Read / unread / delete on the backend, then the bell and the list refresh. Failures go to a toast. */
export function useNotificationActions() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await action()
      return true
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : t('notifications.actionFailed'))
      return false
    } finally {
      setBusy(false)
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    }
  }
  return {
    busy,
    mark: (sel: NotificationSelection, read = true) => run(() => api.markNotifications(sel, read)),
    remove: (sel: NotificationSelection) => run(() => api.deleteNotifications(sel)),
  }
}

/** "Delete N notifications?" (cannot be undone). */
export function DeleteNotificationsDialog({
  open,
  onOpenChange,
  count,
  busy,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  count: number
  busy: boolean
  onConfirm: () => void
}) {
  const { t } = useI18n()
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('notifications.deleteTitle', { count })}</AlertDialogTitle>
          <AlertDialogDescription>{t('notifications.deleteDescription')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>
            {busy && <Loader2 className="animate-spin" />} {t('notifications.delete')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** One notification in full (the bell and the notifications page open it); opening it marks it read. */
/** a bit longer than the dialog's closing animation (duration-100 in ui/dialog.tsx) */
const CLOSE_ANIMATION_MS = 250

export function NotificationDialog({ notification, onClose }: { notification: AppNotification | null; onClose: () => void }) {
  const { t } = useI18n()
  const { draft } = useProject()
  const date = useDateText()
  const actions = useNotificationActions()
  const [deleting, setDeleting] = useState(false)
  const [unreadAgain, setUnreadAgain] = useState(false)
  const { mark } = actions

  // the dialog keeps showing the last notification while its closing animation runs (the parent sets null at once)
  const [kept, setKept] = useState<AppNotification | null>(notification)
  if (notification && notification !== kept) setKept(notification)
  useEffect(() => {
    if (notification) return
    const timer = setTimeout(() => setKept(null), CLOSE_ANIMATION_MS)
    return () => clearTimeout(timer)
  }, [notification])
  const shown = notification ?? kept

  // opening a notification marks it read (once per opening: "mark unread" inside the dialog sticks)
  const openedId = notification?.id
  const openedUnread = notification ? !notification.read : false
  useEffect(() => {
    setUnreadAgain(false)
    if (openedId !== undefined && openedUnread) void mark({ ids: [openedId] })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when another notification opens
  }, [openedId])

  const link = shown ? entityLink(t, draft, shown.entity) : null
  const close = () => onClose()
  return (
    <>
      <Dialog open={!!notification} onOpenChange={(v) => !v && close()}>
        <DialogContent className="sm:max-w-xl">
          {shown && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-start gap-2 pr-6">
                  <KindIcon kind={shown.kind} className="mt-0.5" />
                  <span className="break-words">{shown.title}</span>
                </DialogTitle>
                <DialogDescription>
                  {t(`notifications.kind.${shown.kind}`)} · {date(shown.created_at)}
                </DialogDescription>
              </DialogHeader>
              {shown.description && (
                <p className="max-h-[50vh] overflow-y-auto text-sm break-words whitespace-pre-wrap text-muted-foreground">
                  {shown.description}
                </p>
              )}
              {link ? (
                <Link to={link.to} onClick={close} className="text-sm font-medium underline-offset-4 hover:underline">
                  {link.label}
                </Link>
              ) : (
                shown.entity && <p className="text-xs text-muted-foreground">{t('notifications.entityGone')}</p>
              )}
              <DialogFooter className="gap-2 sm:justify-between">
                <Button variant="ghost" className="text-destructive" onClick={() => setDeleting(true)} disabled={actions.busy}>
                  <Trash2 /> {t('notifications.delete')}
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    disabled={actions.busy || unreadAgain}
                    onClick={async () => {
                      if (await actions.mark({ ids: [shown.id] }, false)) setUnreadAgain(true)
                    }}
                  >
                    {t('notifications.markUnread')}
                  </Button>
                  <Button onClick={close}>{t('common.close')}</Button>
                </div>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
      <DeleteNotificationsDialog
        open={deleting}
        onOpenChange={setDeleting}
        count={1}
        busy={actions.busy}
        onConfirm={async () => {
          if (shown && (await actions.remove({ ids: [shown.id] }))) {
            setDeleting(false)
            close()
          }
        }}
      />
    </>
  )
}
