import { LoaderCircle } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { SearchInput } from '@/components/common/list'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'

export interface PickerItem<K> {
  key: K
  icon: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  disabled?: boolean
}

export interface PickerGroup<K> {
  label?: string
  items: PickerItem<K>[]
}

/** The app's "add" dialog: a search box and a list (optionally in groups) of items with an image, a title, a line
 * below it and an Add button. The caller filters by `query`; it stays open, so several items can be added in a row
 * (onPick may be async: its button spins meanwhile). */
export function PickerDialog<K extends string | number>({
  open,
  onOpenChange,
  title,
  description,
  placeholder,
  query,
  onQuery,
  groups,
  notice,
  empty,
  disabled,
  onPick,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  placeholder: string
  query: string
  onQuery: (q: string) => void
  groups: PickerGroup<K>[]
  notice?: ReactNode // a line above the list (e.g. why nothing can be added)
  empty: string
  disabled?: boolean // every Add button (e.g. the target is full)
  onPick: (key: K) => unknown
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState<K>()
  const pick = async (key: K) => {
    setBusy(key)
    try {
      await onPick(key)
    } finally {
      setBusy(undefined)
    }
  }
  const shown = groups.filter((g) => g.items.length > 0)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <SearchInput value={query} onChange={onQuery} placeholder={placeholder} />
        {notice && <p className="text-sm text-muted-foreground">{notice}</p>}
        {shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <div className="max-h-96 overflow-y-auto pr-3">
            {shown.map((g, k) => (
              <div key={k}>
                {g.label && (
                  <p className="sticky top-0 z-10 bg-background px-2 py-1.5 text-xs font-medium text-muted-foreground">{g.label}</p>
                )}
                <ul className="divide-y">
                  {g.items.map((item) => (
                    <li key={String(item.key)} className="flex items-center justify-between gap-2 py-2">
                      <span className="flex min-w-0 items-center gap-2">
                        {item.icon}
                        <span className="min-w-0">
                          <span className="block truncate">{item.title}</span>
                          {item.subtitle && <span className="block truncate text-xs text-muted-foreground">{item.subtitle}</span>}
                        </span>
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={disabled || item.disabled || busy !== undefined}
                        onClick={() => void pick(item.key)}
                      >
                        {busy === item.key && <LoaderCircle className="animate-spin" />}
                        {t('common.add')}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
