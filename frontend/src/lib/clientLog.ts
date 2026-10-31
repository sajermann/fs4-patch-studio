import { ApiError } from '@/api/client'

// Errors of the interface go to the backend log (POST /api/log), where the support report finds them. The backend
// already logs its own errors, so a failed request is sent only when the backend could not have seen it.

const MAX_PER_PAGE_LOAD = 50 // a loop of errors does not flood the log
const REPEAT_WINDOW_MS = 10_000 // the same message again within this time is skipped

let sent = 0
const lastSent = new Map<string, number>()

function describe(error: unknown) {
  if (error instanceof Error) return { message: `${error.name}: ${error.message}`, detail: error.stack }
  return { message: String(error), detail: undefined }
}

/** Whether the backend logged this error already (it answered with an error of its own). */
const loggedByBackend = (error: unknown) => error instanceof ApiError && error.status !== 0

export function logClientError(context: string, error: unknown, extra?: string) {
  if (loggedByBackend(error)) return
  const { message, detail } = describe(error)
  const text = `${context}: ${message}`
  const now = Date.now()
  if (sent >= MAX_PER_PAGE_LOAD || now - (lastSent.get(text) ?? -Infinity) < REPEAT_WINDOW_MS) return
  sent++
  lastSent.set(text, now)
  const body = {
    level: 'error',
    message: text.slice(0, 4000),
    detail: [detail, extra].filter(Boolean).join('\n').slice(0, 20000) || undefined,
    page: location.pathname + location.search,
  }
  // plain fetch: never an error of its own (the backend may be the thing that is down)
  void fetch('/api/log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(
    () => undefined,
  )
}

/** Browser exceptions nothing caught (event handlers, timers, promises). */
export function installGlobalErrorLog() {
  window.addEventListener('error', (e) =>
    logClientError('uncaught', e.error ?? e.message, e.filename ? `${e.filename}:${e.lineno}:${e.colno}` : undefined),
  )
  window.addEventListener('unhandledrejection', (e) => logClientError('unhandled promise', e.reason))
}
