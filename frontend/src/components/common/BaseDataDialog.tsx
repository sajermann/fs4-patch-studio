import { useQuery } from '@tanstack/react-query'
import { Check, LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ApiError, api } from '@/api/client'
import type { BasePlayer, Player } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useI18n, type TFunction } from '@/i18n'
import { FOOT_LABELS } from '@/lib/labels'
import { OVERALL_SKILLS, computeOverall } from '@/lib/skills'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useLookups } from '@/state/queries'

type Group = 'name' | 'nationality' | 'birthdate' | 'height' | 'weight' | 'foot' | 'skills'

const formatDate = (iso?: string) => (iso ? iso.split('-').reverse().join('/') : '—')
const SKILL_ORDER = [...OVERALL_SKILLS, 'TRI']
const formatSkills = (skills: Record<string, number>) =>
  SKILL_ORDER.filter((k) => skills[k] !== undefined)
    .map((k) => `${k} ${skills[k]}`)
    .join(' · ')

/** The base's first and last names; without them, the full name split at its last space. */
function splitName(rec: BasePlayer): [string, string] {
  if (rec.first_name || rec.last_name) return [rec.first_name ?? '', rec.last_name ?? '']
  const cut = rec.name.lastIndexOf(' ')
  return cut < 0 ? ['', rec.name] : [rec.name.slice(0, cut), rec.name.slice(cut + 1)]
}

/** What each checkbox copies from the base into the player (only groups the base record has). */
function changes(
  t: TFunction,
  rec: BasePlayer,
  player: Player,
  nation: Map<number, string>,
): { key: Group; label: string; patch: Partial<Player>; shown: string }[] {
  const out: { key: Group; label: string; patch: Partial<Player>; shown: string }[] = []
  const [first, last] = splitName(rec)
  // the base's name is how the player is known; kept as the display name only when it is not just first + last
  const display = rec.name !== `${first} ${last}`.trim() ? rec.name : undefined
  out.push({
    key: 'name',
    label: t('base.name'),
    patch: { first_name: first, last_name: last, display_name: display, ...(rec.jersey_name ? { jersey_name: rec.jersey_name } : {}) },
    shown:
      [first, last].filter(Boolean).join(' · ') +
      (display ? ` ${t('base.shownAs', { name: display })}` : '') +
      (rec.jersey_name ? ` · ${t('base.jerseyName', { name: rec.jersey_name })}` : ''),
  })
  if (rec.nation_id !== undefined) {
    out.push({
      key: 'nationality',
      label: t('base.nationality'),
      patch: { fields: { ...player.fields, nationality: rec.nation_id } },
      shown: nation.get(rec.nation_id) ?? rec.nationality ?? String(rec.nation_id),
    })
  }
  if (rec.birth_date) out.push({ key: 'birthdate', label: t('base.birthdate'), patch: { birthdate: rec.birth_date }, shown: formatDate(rec.birth_date) })
  if (rec.height_cm) out.push({ key: 'height', label: t('base.height'), patch: { height: rec.height_cm }, shown: `${rec.height_cm} cm` })
  if (rec.weight_kg) out.push({ key: 'weight', label: t('base.weight'), patch: { weight: rec.weight_kg }, shown: `${rec.weight_kg} kg` })
  if (rec.preferred_foot) {
    const foot = rec.preferred_foot === 'Left' ? 'left' : 'right'
    out.push({ key: 'foot', label: t('base.foot'), patch: { foot }, shown: t(FOOT_LABELS[foot]) })
  }
  if (rec.skills) {
    // converted from the FIFA attributes by the backend (fsapi/ea_players.py): a starting point, editable afterwards
    const bars = rec.skills
    const overall = computeOverall((k) => bars[k])
    out.push({
      key: 'skills',
      label: t('base.skills'),
      patch: { skills: overall === undefined ? { ...bars } : { ...bars, overall } },
      shown: formatSkills(bars) + (overall !== undefined ? ` · ${t('base.overall', { value: overall })}` : ''),
    })
  }
  return out
}

function current(t: TFunction, player: Player, key: Group, nation: Map<number, string>) {
  switch (key) {
    case 'name':
      return [player.first_name, player.last_name].filter(Boolean).join(' · ') || '—'
    case 'birthdate':
      return formatDate(player.birthdate)
    case 'height':
      return player.height ? `${player.height} cm` : t('common.default')
    case 'weight':
      return player.weight ? `${player.weight} kg` : t('common.default')
    case 'foot':
      return player.foot ? t(FOOT_LABELS[player.foot]) : t('common.default')
    case 'nationality': {
      const id = player.fields.nationality
      return id === undefined ? t('common.default') : (nation.get(id) ?? String(id))
    }
    case 'skills':
      return Object.keys(player.skills).length ? formatSkills(player.skills) : t('common.default')
  }
}

/** "Usar dados da base": picks a player of the players base (settings) and copies the checked data into this player
 * (user's request, 26/10: name, nationality, birth date, height, weight, foot and the skill bars converted from the
 * FIFA attributes; all of it stays editable). */
export function BaseDataDialog({ player, open, onOpenChange }: { player: Player; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useI18n()
  const { updatePlayer } = useProject()
  const { nation } = useLookups()
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [picked, setPicked] = useState<number | null>(null)
  const [checked, setChecked] = useState<Set<Group>>(new Set())

  useEffect(() => {
    if (!open) return
    // a real face's id is the EA player id: start from it; otherwise from the player's name
    const start = player.face ? String(player.face.source_id) : `${player.first_name} ${player.last_name}`.trim()
    setQ(start)
    setDebounced(start)
    setPicked(player.face?.source_id ?? null)
  }, [open, player.face, player.first_name, player.last_name])

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q), 250)
    return () => clearTimeout(timer)
  }, [q])

  const results = useQuery({ queryKey: ['players-base', debounced], queryFn: () => api.searchPlayersBase(debounced), enabled: open, retry: false })
  const record = useQuery({
    queryKey: ['players-base-record', picked],
    queryFn: () => api.playersBaseRecord(picked as number),
    enabled: open && picked !== null,
    retry: false,
  })
  const rows = useMemo(() => (record.data ? changes(t, record.data, player, nation) : []), [t, record.data, player, nation])
  useEffect(() => setChecked(new Set(rows.map((r) => r.key))), [rows])

  const apply = () => {
    const patch = Object.assign({}, ...rows.filter((r) => checked.has(r.key)).map((r) => r.patch)) as Partial<Player>
    updatePlayer(player.uid, patch)
    toast.success(t('base.applied', { name: record.data?.name }))
    onOpenChange(false)
  }

  const error = results.error ?? record.error
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('base.title')}</DialogTitle>
          <DialogDescription>{t('base.description')}</DialogDescription>
        </DialogHeader>
        <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('base.search')} autoFocus />
        {error && <p className="text-sm text-destructive">{error instanceof ApiError ? error.message : t('base.readFailed')}</p>}
        <div className="grid gap-3 sm:grid-cols-[1fr_1.3fr]">
          {/* both boxes have a fixed height: the dialog does not grow and shrink while searching */}
          <div className="h-[420px] overflow-y-auto rounded-md border">
            {results.isLoading && <LoaderCircle className="m-3 size-4 animate-spin" />}
            {results.data?.items.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPicked(p.id)}
                className={cn('flex w-full flex-col items-start border-b px-3 py-1.5 text-left text-sm last:border-0 hover:bg-muted', picked === p.id && 'bg-muted')}
              >
                <span className="font-medium">{p.name}</span>
                <span className="text-xs text-muted-foreground">
                  {p.id}
                  {p.club ? ` · ${p.club}` : ''}
                  {p.nationality ? ` · ${p.nationality}` : ''}
                </span>
              </button>
            ))}
            {results.data && !results.data.items.length && <p className="p-3 text-sm text-muted-foreground">{t('base.noResults')}</p>}
            {results.data && results.data.total > results.data.items.length && (
              <p className="p-2 text-xs text-muted-foreground">
                {t('base.showing', { count: results.data.items.length, total: results.data.total })}
              </p>
            )}
          </div>
          <div className="h-[420px] overflow-y-auto rounded-md border p-3 text-sm">
            {picked === null ? (
              <p className="text-muted-foreground">{t('base.pickPlayer')}</p>
            ) : record.isLoading ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : record.data ? (
              <div className="space-y-2">
                <p className="font-medium">
                  {record.data.name} <span className="text-xs text-muted-foreground">({record.data.id})</span>
                </p>
                {rows.length ? (
                  rows.map((r) => (
                    <label key={r.key} className="flex cursor-pointer items-start gap-2">
                      <Checkbox
                        checked={checked.has(r.key)}
                        onCheckedChange={(v) =>
                          setChecked((s) => {
                            const next = new Set(s)
                            if (v) next.add(r.key)
                            else next.delete(r.key)
                            return next
                          })
                        }
                        className="mt-0.5"
                      />
                      <span>
                        <span className="font-medium">{r.label}:</span> {r.shown}
                        <span className="block text-xs text-muted-foreground">{t('base.current', { value: current(t, player, r.key, nation) })}</span>
                      </span>
                    </label>
                  ))
                ) : (
                  <p className="text-muted-foreground">{t('base.noData')}</p>
                )}
              </div>
            ) : null}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={apply} disabled={!record.data || !rows.some((r) => checked.has(r.key))}>
            <Check /> {t('common.apply')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
