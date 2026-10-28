import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { I18nProvider, useI18n } from '@/i18n'
import { ThemeProvider } from '@/lib/theme'
import { LeagueEditPage } from '@/pages/LeagueEditPage'
import { LeaguesPage } from '@/pages/LeaguesPage'
import { PatchesPage } from '@/pages/PatchesPage'
import { PlayerEditPage } from '@/pages/PlayerEditPage'
import { PlayersPage } from '@/pages/PlayersPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SetupPage } from '@/pages/SetupPage'
import { StadiumsPage } from '@/pages/StadiumsPage'
import { TeamEditPage } from '@/pages/TeamEditPage'
import { TeamsPage } from '@/pages/TeamsPage'
import { ProjectProvider } from '@/state/project'
import { useStatus } from '@/state/queries'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } })

function Gate() {
  const { t } = useI18n()
  const { data: status, error } = useStatus()
  if (error) return <div className="p-8 text-destructive">{t('app.serverDown')}</div>
  if (!status) {
    return (
      <div className="flex min-h-svh items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="animate-spin" /> {t('common.loading')}
      </div>
    )
  }
  // first run (or the originals / folders / notice changed): nothing else opens before the setup screen
  if (status.setup.required) return <SetupPage status={status} />
  return (
    <ProjectProvider>
      <Routes>
        <Route path="setup" element={<SetupPage status={status} />} />
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/teams" replace />} />
          <Route path="leagues" element={<LeaguesPage />} />
          <Route path="leagues/:key" element={<LeagueEditPage />} />
          <Route path="teams" element={<TeamsPage />} />
          <Route path="teams/:uid" element={<TeamEditPage />} />
          <Route path="players" element={<PlayersPage />} />
          <Route path="players/:uid" element={<PlayerEditPage />} />
          <Route path="stadiums" element={<StadiumsPage />} />
          <Route path="patches" element={<PatchesPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/teams" replace />} />
        </Route>
      </Routes>
    </ProjectProvider>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <BrowserRouter>
              <Gate />
            </BrowserRouter>
            <Toaster richColors position="bottom-right" />
          </TooltipProvider>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}
