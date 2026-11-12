import { MutationCache, QueryCache, QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { AppShell } from '@/components/layout/AppShell'
import { ErrorBoundary } from '@/components/layout/ErrorBoundary'
import { LoadError } from '@/components/layout/LoadError'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import type { Config } from '@/api/types'
import { I18nProvider, onLanguageChange, translate, useI18n } from '@/i18n'
import { logClientError } from '@/lib/clientLog'
import { flushNotifications, onNotificationsChanged } from '@/lib/notify'
import { ThemeProvider } from '@/lib/theme'
import { BallEditPage } from '@/pages/BallEditPage'
import { BallsPage } from '@/pages/BallsPage'
import { BootEditPage } from '@/pages/BootEditPage'
import { BootsPage } from '@/pages/BootsPage'
import { GloveEditPage } from '@/pages/GloveEditPage'
import { GlovesPage } from '@/pages/GlovesPage'
import { LeagueEditPage } from '@/pages/LeagueEditPage'
import { LeaguesPage } from '@/pages/LeaguesPage'
import { PatchesPage } from '@/pages/PatchesPage'
import { PlayerEditPage } from '@/pages/PlayerEditPage'
import { NotificationsPage } from '@/pages/NotificationsPage'
import { PlayersPage } from '@/pages/PlayersPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SetupPage } from '@/pages/SetupPage'
import { StadiumPage } from '@/pages/StadiumPage'
import { StadiumsPage } from '@/pages/StadiumsPage'
import { WorldTourPage } from '@/pages/WorldTourPage'
import { TeamEditPage } from '@/pages/TeamEditPage'
import { TeamsPage } from '@/pages/TeamsPage'
import { ProjectProvider } from '@/state/project'
import { useStatus } from '@/state/queries'

/** Queries whose screen shows their error itself (meta.errorShown): the others say it in a toast, so nothing fails
 * silently. Every failure goes to the log (clientLog skips the ones the backend logged already). */
const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
  queryCache: new QueryCache({
    onError: (error, query) => {
      logClientError(`query ${JSON.stringify(query.queryKey)}`, error)
      if (!query.meta?.errorShown) toast.error(error.message || translate('app.unexpectedError'), { id: query.queryHash })
    },
  }),
  mutationCache: new MutationCache({ onError: (error) => logClientError('mutation', error) }),
})

/** The interface language lives in the backend's settings: the saved one wins when the app opens (the browser's copy
 * is only for the first paint), and every switch is saved there (new notifications are written in it). */
function LanguageSync({ config }: { config: Config }) {
  const { lang, setLang } = useI18n()
  const queryClient = useQueryClient()
  const applied = useRef(false)
  useEffect(() => {
    if (applied.current) return
    applied.current = true
    if (config.language && config.language !== lang) setLang(config.language)
    else if (!config.language) void api.saveLanguage(lang).catch((e) => logClientError('save language', e))
  }, [config.language, lang, setLang])
  useEffect(
    () =>
      onLanguageChange((next) => {
        api
          .saveLanguage(next)
          .then(() => queryClient.invalidateQueries({ queryKey: ['status'] }))
          .catch((e) => logClientError('save language', e))
      }),
    [queryClient],
  )
  return null
}

/** The bell and the notifications page refresh whenever a toast reaches the backend; the ones queued while the
 * backend was down are sent as soon as the app talks to it again. */
function NotificationsSync() {
  const queryClient = useQueryClient()
  useEffect(() => {
    void flushNotifications()
    return onNotificationsChanged(() => void queryClient.invalidateQueries({ queryKey: ['notifications'] }))
  }, [queryClient])
  return null
}

function Gate() {
  const { t } = useI18n()
  const { data: status, error, refetch } = useStatus()
  if (error && !status) return <LoadError page error={error} title={t('app.startFailed')} onRetry={() => void refetch()} />
  if (!status) {
    return (
      <div className="flex min-h-svh items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="animate-spin" /> {t('common.loading')}
      </div>
    )
  }
  // first run (or the originals / folders / notice changed): nothing else opens before the setup screen
  const sync = (
    <>
      <LanguageSync config={status.config} />
      <NotificationsSync />
    </>
  )
  if (status.setup.required)
    return (
      <>
        {sync}
        <SetupPage status={status} />
      </>
    )
  return (
    <ProjectProvider>
      {sync}
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
          <Route path="boots" element={<BootsPage />} />
          <Route path="boots/:uid" element={<BootEditPage />} />
          <Route path="gloves" element={<GlovesPage />} />
          <Route path="gloves/:uid" element={<GloveEditPage />} />
          <Route path="balls" element={<BallsPage />} />
          <Route path="balls/:uid" element={<BallEditPage />} />
          <Route path="stadiums" element={<StadiumsPage />} />
          <Route path="stadiums/:id" element={<StadiumPage />} />
          <Route path="world-tour" element={<WorldTourPage />} />
          <Route path="patches" element={<PatchesPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
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
              <ErrorBoundary page>
                <Gate />
              </ErrorBoundary>
            </BrowserRouter>
            <Toaster richColors position="bottom-right" />
          </TooltipProvider>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}
