import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '@/api/client'
import { useI18n } from '@/i18n'

// Original game data and valid values never change while the app runs.
const forever = { staleTime: Infinity, gcTime: Infinity, retry: false } as const
// the app shell shows their error on the page instead of the pages (AppShell), no toast (App.tsx)
const shownByShell = { meta: { errorShown: true } } as const

export const useStatus = () => useQuery({ queryKey: ['status'], queryFn: api.status, retry: 1, ...shownByShell })
export const useCatalog = () => useQuery({ queryKey: ['catalog'], queryFn: api.catalog, ...forever, ...shownByShell })
export const useOriginalLeagues = () =>
  useQuery({ queryKey: ['originals', 'leagues'], queryFn: api.originalLeagues, ...forever, ...shownByShell })
export const useOriginalTeams = () =>
  useQuery({ queryKey: ['originals', 'teams'], queryFn: api.originalTeams, ...forever, ...shownByShell })
export const useOriginalStadiums = () =>
  useQuery({ queryKey: ['originals', 'stadiums'], queryFn: api.originalStadiums, ...forever, ...shownByShell })

export const useOriginalBoots = () =>
  useQuery({ queryKey: ['originals', 'boots'], queryFn: api.originalBoots, ...forever, ...shownByShell })

export const useOriginalBalls = () =>
  useQuery({ queryKey: ['originals', 'balls'], queryFn: api.originalBalls, ...forever, ...shownByShell })

export const useOriginalGloves = () =>
  useQuery({ queryKey: ['originals', 'gloves'], queryFn: api.originalGloves, ...forever, ...shownByShell })

export function useOriginalPlayers(params: { team?: number; q?: string; offset?: number; limit?: number }, enabled = true) {
  return useQuery({
    queryKey: ['originals', 'players', params],
    queryFn: () => api.originalPlayers(params),
    enabled,
    ...forever,
    placeholderData: (prev) => prev,
  })
}

/** Player.fields.nationality of a player with no nationality (a nation id the game does not have). */
export const NO_NATIONALITY = 0

/** Lookup helpers built from the catalog and the original lists. */
export function useLookups() {
  const { t } = useI18n()
  const leagues = useOriginalLeagues().data
  const teams = useOriginalTeams().data
  const catalog = useCatalog().data
  return useMemo(
    () => ({
      originalLeague: new Map((leagues ?? []).map((l) => [l.id, l])),
      originalTeam: new Map((teams ?? []).map((tm) => [tm.id, tm])),
      position: new Map((catalog?.positions ?? []).map((p) => [p.code, p.abbr])),
      nation: new Map([[NO_NATIONALITY, t('playerEdit.noNationality')], ...(catalog?.nations ?? []).map((n) => [n.id, n.name] as [number, string])]),
    }),
    [leagues, teams, catalog, t],
  )
}
