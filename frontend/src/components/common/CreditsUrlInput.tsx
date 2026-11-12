import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { normalizeWebLink } from '@/lib/weblink'

/** Field of a credits link: what is typed is kept in the entry only when it is a web address (http/https; 'site.com'
 * gets https://), empty clears it; anything else shows an error and leaves the entry as it was. Give it a `key` of
 * the entry, so another entry starts from its own link. */
export function CreditsUrlInput({ value, onChange, id }: { value?: string | null; onChange: (url: string | undefined) => void; id?: string }) {
  const { t } = useI18n()
  const [text, setText] = useState(value ?? '')
  const bad = !!text.trim() && !normalizeWebLink(text)
  return (
    <>
      <Input
        id={id}
        value={text}
        placeholder="https://"
        aria-invalid={bad}
        className="font-mono"
        onChange={(e) => {
          setText(e.target.value)
          if (!e.target.value.trim()) onChange(undefined)
          else {
            const url = normalizeWebLink(e.target.value)
            if (url) onChange(url)
          }
        }}
        onBlur={() => {
          const url = normalizeWebLink(text)
          if (url) setText(url) // shows the address as it is kept
        }}
      />
      {bad && <p className="text-xs text-destructive">{t('credits.badLink')}</p>}
    </>
  )
}
