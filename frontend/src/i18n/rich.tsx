import { Fragment, type ReactNode } from 'react'

/** Renders a dictionary text with light markup: `code` and **bold** (so long help texts keep their formatting
 * without splitting them into many keys). */
export function rich(text: string): ReactNode {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/).map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`'))
      return (
        <code key={i} className="font-mono text-foreground">
          {part.slice(1, -1)}
        </code>
      )
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>
    return <Fragment key={i}>{part}</Fragment>
  })
}
