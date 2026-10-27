import { ArrowLeft } from 'lucide-react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'

/** Where an edit page's "←" button goes: the page the user came from (path + filters), with that page's own history
 * state, so a chain like Liga → Time → Jogador walks back step by step. */
export type Back = { to: string; label: string; state?: unknown }

type BackState = { back?: Back; returning?: boolean }

/** Navigation options for opening an item from the current page: the item's "←" comes back here, labeled `label`. */
export function useFrom(label: string) {
  const loc = useLocation()
  return { state: { back: { to: loc.pathname + loc.search, label, state: loc.state } } satisfies BackState }
}

/** The "←" target of the current page: where the user came from, or `fallback` when opened by a direct link. */
export function useBack(fallback: Back): Back {
  return (useLocation().state as BackState | null)?.back ?? fallback
}

/** History state for going back: the origin's own state, marked so its list restores the scroll. */
export function backState(back: Back) {
  return { ...(back.state as object | undefined), returning: true }
}

/** True when the current page was reached through a "←" (or after deleting the item that was open). */
export function useReturning() {
  return Boolean((useLocation().state as BackState | null)?.returning)
}

/** Goes to `back` (e.g. after deleting the open item). */
export function useGoBack() {
  const navigate = useNavigate()
  return (back: Back) => navigate(back.to, { state: backState(back) })
}

/** Navigation options that keep the current "←" (e.g. opening a copy of the open item). */
export function useKeepBack() {
  const state = useLocation().state as BackState | null
  return { state: state?.back ? { back: state.back } : undefined }
}

export function BackButton({ back }: { back: Back }) {
  return (
    <Button variant="ghost" size="sm" asChild>
      <Link to={back.to} state={backState(back)}>
        <ArrowLeft /> {back.label}
      </Link>
    </Button>
  )
}

/** Props for a page's `<Tabs>`: the open tab lives in the URL (?tab=…), so coming back to the page reopens it. */
export function useTabParam(fallback: string) {
  const [params, setParams] = useSearchParams()
  const state = useLocation().state // keeps the page's "←"
  return {
    value: params.get('tab') ?? fallback,
    onValueChange: (tab: string) =>
      setParams(
        (p) => {
          const next = new URLSearchParams(p)
          if (tab === fallback) next.delete('tab')
          else next.set('tab', tab)
          return next
        },
        { replace: true, state },
      ),
  }
}
