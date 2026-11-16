import * as React from "react"

/** Whether the dialog around is open (set by Dialog / AlertDialog in this folder). */
const OpenContext = React.createContext(true)

/** The open state of a dialog root, controlled (`open`) or not (`defaultOpen` + its own changes), given to its
 * content through OpenContext. */
export function useOpenState(
  open: boolean | undefined,
  defaultOpen: boolean | undefined,
  onOpenChange: ((open: boolean) => void) | undefined
) {
  const [inner, setInner] = React.useState(defaultOpen ?? false)
  const change = React.useCallback(
    (next: boolean) => {
      setInner(next)
      onOpenChange?.(next)
    },
    [onOpenChange]
  )
  return { isOpen: open ?? inner, onOpenChange: change, Provider: OpenContext.Provider }
}

/** The dialog content as it was while open. The screens usually clear the data a dialog shows in the same click
 * that closes it (cancel, X, confirm); the content stays mounted for the closing animation, so without this it
 * would empty or change (names, counts, lists) while fading out. Kept in a ref on purpose: the last open render is
 * shown as it was, and a new opening shows the new content right away. */
export function useContentWhileClosing(children: React.ReactNode) {
  const open = React.useContext(OpenContext)
  const last = React.useRef(children)
  if (open) last.current = children
  return open ? children : last.current
}
