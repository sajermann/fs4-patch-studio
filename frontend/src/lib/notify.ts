import type { ReactNode } from 'react'
import { toast as sonner, type ExternalToast } from 'sonner'
import { api, ApiError } from '@/api/client'
import type { NewNotification, NotificationKind } from '@/api/types'
import { currentLang } from '@/i18n'

/** Toast options plus what the notification center keeps: `entity` = uid of the league/team/player the message is
 * about (the bell and the notifications page link to it). */
export type NotifyOptions = ExternalToast & { entity?: string | null }

const QUEUE_KEY = 'fsmod.notifications.pending'
const RETRY_MS = 15000

const changeListeners = new Set<() => void>()

/** Called after a notification reaches the backend (the bell and the notifications page refresh). */
export function onNotificationsChanged(listener: () => void) {
  changeListeners.add(listener)
  return () => {
    changeListeners.delete(listener)
  }
}

function readQueue(): NewNotification[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? (parsed as NewNotification[]) : []
  } catch {
    return []
  }
}

function writeQueue(items: NewNotification[]) {
  try {
    if (items.length) localStorage.setItem(QUEUE_KEY, JSON.stringify(items))
    else localStorage.removeItem(QUEUE_KEY)
  } catch {
    /* storage blocked: the queued ones are lost when the page reloads */
  }
}

// notifications waiting for the backend, kept in memory too in case the storage is blocked
let pending: NewNotification[] = readQueue()
let flushing = false
let retryTimer: ReturnType<typeof setTimeout> | undefined

function scheduleRetry() {
  if (retryTimer === undefined && pending.length) {
    retryTimer = setTimeout(() => {
      retryTimer = undefined
      void flushNotifications()
    }, RETRY_MS)
  }
}

/** Sends the queued notifications, oldest first; stops at the first one the backend does not take (still down). */
export async function flushNotifications() {
  if (flushing || !pending.length) return
  flushing = true
  let sent = 0
  try {
    while (pending.length) {
      try {
        await api.addNotification(pending[0])
      } catch (e) {
        // backend down (no answer; through the dev server's proxy, a 5xx): try again later; refused (4xx): drop it,
        // it would never get in
        if (!(e instanceof ApiError) || e.status === 0 || e.status >= 500) break
        console.warn('notification refused', e)
      }
      pending = pending.slice(1)
      writeQueue(pending)
      sent++
    }
  } finally {
    flushing = false
    if (sent) changeListeners.forEach((listener) => listener())
    scheduleRetry()
  }
}

const text = (value: ReactNode | (() => ReactNode)): string | undefined => {
  const v = typeof value === 'function' ? value() : value
  return typeof v === 'string' || typeof v === 'number' ? String(v) : undefined
}

function record(kind: NotificationKind, message: ReactNode | (() => ReactNode), options?: NotifyOptions) {
  const title = text(message)
  if (!title) return // a toast that is not text (none today) has nothing the list could show
  const description = options?.description !== undefined ? text(options.description) : undefined
  pending = [
    ...pending,
    {
      kind,
      title,
      ...(description ? { description } : {}),
      ...(options?.entity ? { entity: options.entity } : {}),
      created_at: new Date().toISOString(),
      language: currentLang(),
    },
  ]
  writeQueue(pending)
  void flushNotifications()
}

type Show = (message: ReactNode | (() => ReactNode), options?: NotifyOptions) => string | number

function shower(kind: NotificationKind, show: Show): Show {
  return (message, options) => {
    record(kind, message, options)
    const { entity: _entity, ...rest } = options ?? {}
    return show(message, rest)
  }
}

/** The app's toasts: same calls as sonner's `toast`, and every message also goes to the notification center (kept
 * by the backend; queued in the browser while the backend does not answer). Import this, never sonner directly. */
export const toast = Object.assign((message: ReactNode | (() => ReactNode), options?: NotifyOptions) => shower('info', sonner)(message, options), {
  success: shower('success', sonner.success),
  error: shower('error', sonner.error),
  warning: shower('warning', sonner.warning),
  info: shower('info', sonner.info),
  dismiss: sonner.dismiss,
})

scheduleRetry()
