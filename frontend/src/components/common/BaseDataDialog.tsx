import { Check } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from '@/lib/notify'
import type { OriginalPlayer, Player } from '@/api/types'
import { OriginalBadge } from '@/components/common/form'
import { matches } from '@/components/common/list'
import { OriginalPlayerAvatar, PlayerAvatar } from '@/components/common/PlayerPhoto'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useI18n, type TFunction } from '@/i18n'
import { FOOT_LABELS } from '@/lib/labels'
import { useGamePlayers, useTeamName } from '@/lib/members'
import { OVERALL_SKILLS, computeOverall } from '@/lib/skills'
import { cn } from '@/lib/utils'
import { useProject, useSameAsGame } from '@/state/project'
import { useLookups } from '@/state/queries'

type Group = 'name' | 'nationality' | 'birthdate' | 'height' | 'weight' | 'foot' | 'skills'

/** A player the data can come from: one of the project (new or an edited original) or one of the game's as the game
 * has him. Values left undefined are the template's defaults (project players) and are not offered. */
interface Source {
  key: string
  name: string
  searched: string[] // what the search looks at (names, jersey name, id)
  detail: string // team · id, under the name
  photo: { project: Player } | { game: OriginalPlayer } // for the avatar
  original: boolean // one of the game's players as the game has him
  entry?: string // uid of a project entry (its badge says whether it edits an original)
  first_name: string
  last_name: string
  display_name?: string
  jersey_name?: string
  nationality?: number
  birthdate?: string
  height?: number
  weight?: number
  foot?: 'right' | 'left'
  skills: Record<string, number>
}

const RESULTS = 100 // rows listed at once; the search narrows the rest
const formatDate = (iso?: string) => (iso ? iso.split('-').reverse().join('/') : '—')
const SKILL_ORDER = [...OVERALL_SKILLS, 'TRI']
const formatSkills = (skills: Record<string, number>) =>
  SKILL_ORDER.filter((k) => skills[k] !== undefined)
    .map((k) => `${k} ${skills[k]}`)
    .join(' · ')

/** What each checkbox copies from the chosen player into this one (only the groups the chosen player has). */
function changes(
  t: TFunction,
  src: Source,
  player: Player,
  nation: Map<number, string>,
): { key: Group; label: string; patch: Partial<Player>; shown: string }[] {
  const out: { key: Group; label: string; patch: Partial<Player>; shown: string }[] = []
  out.push({
    key: 'name',
    label: t('base.name'),
    patch: {
      first_name: src.first_name,
      last_name: src.last_name,
      display_name: src.display_name,
      ...(src.jersey_name ? { jersey_name: src.jersey_name } : {}),
    },
    shown:
      [src.first_name, src.last_name].filter(Boolean).join(' · ') +
      (src.display_name ? ` ${t('base.shownAs', { name: src.display_name })}` : '') +
      (src.jersey_name ? ` · ${t('base.jerseyName', { name: src.jersey_name })}` : ''),
  })
  if (src.nationality !== undefined) {
    out.push({
      key: 'nationality',
      label: t('base.nationality'),
      patch: { fields: { ...player.fields, nationality: src.nationality } },
      shown: nation.get(src.nationality) ?? String(src.nationality),
    })
  }
  if (src.birthdate) out.push({ key: 'birthdate', label: t('base.birthdate'), patch: { birthdate: src.birthdate }, shown: formatDate(src.birthdate) })
  if (src.height) out.push({ key: 'height', label: t('base.height'), patch: { height: src.height }, shown: `${src.height} cm` })
  if (src.weight) out.push({ key: 'weight', label: t('base.weight'), patch: { weight: src.weight }, shown: `${src.weight} kg` })
  if (src.foot) out.push({ key: 'foot', label: t('base.foot'), patch: { foot: src.foot }, shown: t(FOOT_LABELS[src.foot]) })
  if (Object.keys(src.skills).length) {
    const skills = { ...src.skills }
    if (skills.overall === undefined) {
      const overall = computeOverall((k) => skills[k])
      if (overall !== undefined) skills.overall = overall
    }
    out.push({
      key: 'skills',
      label: t('base.skills'),
      patch: { skills },
      shown: formatSkills(skills) + (skills.overall !== undefined ? ` · ${t('base.overall', { value: skills.overall })}` : ''),
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

/** Every player the data can be copied from: the project's (an edited original once, as the project has him) and the
 * game's own, but never the player being edited. */
function useSources(player: Player, open: boolean): Source[] {
  const { t } = useI18n()
  const { draft } = useProject()
  const sameAsGame = useSameAsGame()
  const games = useGamePlayers()
  const teamName = useTeamName()
  const { originalTeam } = useLookups()
  return useMemo(() => {
    if (!open) return []
    const mine = draft.players.filter((p) => !sameAsGame(p.uid) && p.uid !== player.uid)
    const edited = new Set(draft.players.filter((p) => !sameAsGame(p.uid)).flatMap((p) => (p.original_id != null ? [p.original_id] : [])))
    const fromProject = mine.map((p): Source => {
      const full = `${p.first_name} ${p.last_name}`.trim()
      const id = p.original_id ?? p.player_id
      return {
        key: `p:${p.uid}`,
        name: p.display_name || full || t('common.unnamed'),
        searched: [p.display_name ?? '', full, p.jersey_name ?? '', id != null ? String(id) : ''],
        detail: [p.teams.length ? teamName(p.teams[0].team) : t('players.freeAgent'), id].filter((v) => v != null).join(' · '),
        photo: { project: p },
        original: false,
        entry: p.original_id != null ? p.uid : undefined,
        first_name: p.first_name,
        last_name: p.last_name,
        display_name: p.display_name || undefined,
        jersey_name: p.jersey_name || undefined,
        nationality: p.fields.nationality,
        birthdate: p.birthdate,
        height: p.height,
        weight: p.weight,
        foot: p.foot,
        skills: p.skills,
      }
    })
    const fromGame = [...games.values()]
      .filter((p) => !edited.has(p.id) && p.id !== player.original_id)
      .map((p): Source => {
        const full = `${p.first_name} ${p.last_name}`.trim()
        return {
          key: `g:${p.id}`,
          name: p.display_name || full,
          searched: [p.display_name, full, p.jersey_name ?? '', String(p.id)],
          detail: [p.teams.length ? (originalTeam.get(p.teams[0])?.name ?? p.teams[0]) : t('players.freeAgent'), p.id].join(' · '),
          photo: { game: p },
          original: true,
          first_name: p.first_name,
          last_name: p.last_name,
          display_name: p.display_name && p.display_name !== full ? p.display_name : undefined,
          jersey_name: p.jersey_name ?? undefined,
          nationality: p.nationality,
          birthdate: p.birthdate ?? undefined,
          height: p.height,
          weight: p.weight,
          foot: p.foot,
          skills: p.skills,
        }
      })
    return [...fromProject, ...fromGame]
  }, [open, draft.players, sameAsGame, player.uid, player.original_id, games, teamName, originalTeam, t])
}

/** "Usar dados da base": picks one of the players already registered (the project's or the game's) and copies the
 * checked data into this player (user's request, 16/11/2026: name, nationality, birth date, height, weight, foot and
 * the skill bars; all of it stays editable). */
export function BaseDataDialog({ player, open, onOpenChange }: { player: Player; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useI18n()
  const { updatePlayer } = useProject()
  const { nation } = useLookups()
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [picked, setPicked] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<Group>>(new Set())
  const sources = useSources(player, open)

  useEffect(() => {
    if (!open) return
    // start from the player's own name: the same player elsewhere (the game's, another team's) comes first
    const start = player.display_name || `${player.first_name} ${player.last_name}`.trim()
    setQ(start)
    setDebounced(start)
    setPicked(null)
  }, [open, player.display_name, player.first_name, player.last_name])

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q), 250)
    return () => clearTimeout(timer)
  }, [q])

  const found = useMemo(() => sources.filter((s) => matches(debounced, ...s.searched)), [sources, debounced])
  const source = sources.find((s) => s.key === picked)
  const rows = useMemo(() => (source ? changes(t, source, player, nation) : []), [t, source, player, nation])
  useEffect(() => setChecked(new Set(rows.map((r) => r.key))), [rows])

  const apply = () => {
    if (!source) return
    const patch = Object.assign({}, ...rows.filter((r) => checked.has(r.key)).map((r) => r.patch)) as Partial<Player>
    updatePlayer(player.uid, patch)
    toast.success(t('base.applied', { name: source.name }))
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent width="lg">
        <DialogHeader>
          <DialogTitle>{t('base.title')}</DialogTitle>
          <DialogDescription>{t('base.description')}</DialogDescription>
        </DialogHeader>
        <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('base.search')} autoFocus />
        <div className="grid gap-3 sm:grid-cols-[1fr_1.3fr]">
          {/* both boxes have a fixed height: the dialog does not grow and shrink while searching */}
          <div className="h-[420px] overflow-y-auto rounded-md border">
            {found.slice(0, RESULTS).map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setPicked(s.key)}
                className={cn('flex w-full items-center gap-2 border-b px-3 py-1.5 text-left text-sm last:border-0 hover:bg-muted', picked === s.key && 'bg-muted')}
              >
                {'project' in s.photo ? (
                  <PlayerAvatar player={s.photo.project} className="size-7" />
                ) : (
                  <OriginalPlayerAvatar player={s.photo.game} className="size-7" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 font-medium">
                    <span className="truncate">{s.name}</span>
                    {(s.original || s.entry) && <OriginalBadge entry={s.entry} />}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">{s.detail}</span>
                </span>
              </button>
            ))}
            {!found.length && <p className="p-3 text-sm text-muted-foreground">{t('base.noResults')}</p>}
            {found.length > RESULTS && <p className="p-2 text-xs text-muted-foreground">{t('base.showing', { count: RESULTS, total: found.length })}</p>}
          </div>
          <div className="h-[420px] overflow-y-auto rounded-md border p-3 text-sm">
            {!source ? (
              <p className="text-muted-foreground">{t('base.pickPlayer')}</p>
            ) : (
              <div className="space-y-2">
                <p className="font-medium">{source.name}</p>
                {rows.map((r) => (
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
                ))}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={apply} disabled={!source || !rows.some((r) => checked.has(r.key))}>
            <Check /> {t('common.apply')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
