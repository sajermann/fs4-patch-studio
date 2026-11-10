import {
  AlertTriangle,
  Footprints,
  Globe,
  Hand,
  Heart,
  Landmark,
  Loader2,
  Puzzle,
  Settings,
  Shield,
  Trophy,
  Users,
  Volleyball,
} from 'lucide-react'
import { APP_NAME, APP_VERSION, AUTHOR_GITHUB, AUTHOR_NAME, DONATE_URL, REPO_URL } from '@/lib/about'
import { Button } from '@/components/ui/button'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useI18n, type MessageKey } from '@/i18n'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useCatalog, useOriginalLeagues, useOriginalStadiums, useOriginalTeams, useStatus } from '@/state/queries'
import { ErrorBoundary } from './ErrorBoundary'
import { LoadError } from './LoadError'
import { PreferencesMenu } from './PreferencesMenu'
import { ProjectActions } from './ProjectActions'

const NAV: { to: string; label: MessageKey; icon: typeof Trophy }[] = [
  { to: '/leagues', label: 'nav.leagues', icon: Trophy },
  { to: '/teams', label: 'nav.teams', icon: Shield },
  { to: '/players', label: 'nav.players', icon: Users },
  { to: '/boots', label: 'nav.boots', icon: Footprints },
  { to: '/gloves', label: 'nav.gloves', icon: Hand },
  { to: '/balls', label: 'nav.balls', icon: Volleyball },
  { to: '/stadiums', label: 'nav.stadiums', icon: Landmark },
  { to: '/world-tour', label: 'nav.worldTour', icon: Globe },
  { to: '/patches', label: 'nav.patches', icon: Puzzle },
]

/** GitHub's mark (lucide has no brand icons); takes the text color. */
function GithubMark() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" fill="currentColor" className="size-4">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

function NavItem({ to, label, icon: Icon }: { to: string; label: MessageKey; icon: typeof Trophy }) {
  const { t } = useI18n()
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent',
          isActive && 'bg-accent font-medium',
        )
      }
    >
      <Icon className="size-4" />
      {t(label)}
    </NavLink>
  )
}

/** What changed in the game since the app looked at it (ReStreet update, files touched by hand). */
function GameWarnings() {
  const { t } = useI18n()
  const game = useStatus().data?.setup.game
  if (!game) return null
  const messages = [
    game.changed.length > 0 && t('shell.patchChanged', { count: game.changed.length }),
    !game.tested &&
      t('shell.untestedVersion', {
        version: game.version ?? t('shell.unknownVersion'),
        tested: game.tested_versions,
      }),
  ].filter(Boolean) as string[]
  if (!messages.length) return null
  return (
    <div className="space-y-1 border-b border-amber-500/40 bg-amber-500/10 px-6 py-2 text-sm text-amber-800 dark:text-amber-300">
      {messages.map((m) => (
        <p key={m} className="flex items-center gap-2">
          <AlertTriangle className="size-4 shrink-0" /> {m}
        </p>
      ))}
    </div>
  )
}

export function AppShell() {
  const { t } = useI18n()
  const { draft, loaded, opened } = useProject()
  // pages assume the project and the original game data are available
  const queries = [useCatalog(), useOriginalLeagues(), useOriginalTeams(), useOriginalStadiums()] as const
  const [catalog, leagues, teams, stadiums] = queries.map((q) => q.data) as [
    (typeof queries)[0]['data'],
    (typeof queries)[1]['data'],
    (typeof queries)[2]['data'],
    (typeof queries)[3]['data'],
  ]
  const failed = queries.find((q) => q.error)?.error
  const ready = loaded && !!catalog && !!leagues && !!teams
  const { pathname } = useLocation()
  const counts: Record<string, number> = {
    '/leagues': draft.leagues.filter((e) => !opened.has(e.uid)).length,
    '/teams': draft.teams.filter((e) => !opened.has(e.uid)).length, // originals only opened are not in the project
    '/players': draft.players.filter((e) => !opened.has(e.uid)).length,
    '/boots': (draft.boots ?? []).filter((e) => !opened.has(e.uid)).length,
    '/gloves': (draft.gloves ?? []).filter((e) => !opened.has(e.uid)).length,
    '/balls': (draft.balls ?? []).filter((e) => !opened.has(e.uid)).length,
    '/stadiums': stadiums?.length ?? 0,
    '/world-tour': (draft.world_tour?.dark?.length ?? 0) + (draft.world_tour?.white?.length ?? 0),
    '/patches': Object.values(draft.game_patches ?? {}).filter(Boolean).length,
  }
  return (
    // screen height: the menu stays put and only the page area scrolls (list pages scroll inside their table)
    <div className="flex h-svh overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col overflow-y-auto border-r bg-muted/30 p-3">
        <div className="mb-6 px-3 pt-2">
          <p className="text-sm font-semibold">{APP_NAME}</p>
          <p className="text-xs text-muted-foreground">{t('app.subtitle')}</p>
        </div>
        <nav className="space-y-1">
          {NAV.map((n) => (
            <div key={n.to} className="relative">
              <NavItem {...n} />
              {counts[n.to] > 0 && (
                <span className="absolute top-2 right-3 text-xs text-muted-foreground tabular-nums">{counts[n.to]}</span>
              )}
            </div>
          ))}
        </nav>
        <div className="mt-auto space-y-2">
          <NavItem to="/settings" label="nav.settings" icon={Settings} />
          <div className="px-1">
            <PreferencesMenu />
          </div>
          <div className="space-y-0.5 px-3 pt-2 text-xs text-muted-foreground">
            <p className="flex items-center justify-between gap-2">
              <span>
                {t('app.credits')}{' '}
                <a href={AUTHOR_GITHUB} target="_blank" rel="noreferrer" className="underline-offset-2 hover:text-foreground hover:underline">
                  {AUTHOR_NAME}
                </a>
              </span>
              {/* the source code: an icon only, the label goes to the tooltip and screen readers */}
              <Button variant="ghost" size="icon-sm" asChild>
                <a href={REPO_URL} target="_blank" rel="noreferrer" title={t('app.sourceCode')} aria-label={t('app.sourceCode')}>
                  <GithubMark />
                </a>
              </Button>
            </p>
            <p>
              {t('app.version')} {APP_VERSION}
            </p>
            <Button variant="outline" size="sm" className="mt-2 w-full" asChild>
              <a href={DONATE_URL} target="_blank" rel="noreferrer">
                <Heart className="text-rose-500" /> {t('app.donate')}
              </a>
            </Button>
          </div>
        </div>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="z-10 flex shrink-0 justify-end border-b bg-background/95 px-6 py-3 backdrop-blur">
          <ProjectActions />
        </header>
        <GameWarnings />
        <main className="min-h-0 flex-1 overflow-auto p-6">
          {failed ? (
            <LoadError
              error={failed}
              title={t('shell.loadGameFailed')}
              onRetry={() => queries.forEach((q) => q.error && void q.refetch())}
            />
          ) : ready ? (
            <ErrorBoundary resetKey={pathname}>
              <Outlet />
            </ErrorBoundary>
          ) : (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="animate-spin" /> {t('shell.loadingGame')}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
