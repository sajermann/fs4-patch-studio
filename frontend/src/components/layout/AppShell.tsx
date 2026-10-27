import { AlertTriangle, Landmark, Loader2, Settings, Shield, Trophy, Users } from 'lucide-react'
import { APP_NAME, AUTHOR_GITHUB, AUTHOR_NAME, REPO_URL } from '@/lib/about'
import { NavLink, Outlet } from 'react-router-dom'
import { useI18n, type MessageKey } from '@/i18n'
import { cn } from '@/lib/utils'
import { useProject } from '@/state/project'
import { useCatalog, useOriginalLeagues, useOriginalStadiums, useOriginalTeams, useStatus } from '@/state/queries'
import { PreferencesMenu } from './PreferencesMenu'
import { ProjectActions } from './ProjectActions'

const NAV: { to: string; label: MessageKey; icon: typeof Trophy }[] = [
  { to: '/leagues', label: 'nav.leagues', icon: Trophy },
  { to: '/teams', label: 'nav.teams', icon: Shield },
  { to: '/players', label: 'nav.players', icon: Users },
  { to: '/stadiums', label: 'nav.stadiums', icon: Landmark },
]

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
  const { draft, loaded } = useProject()
  // pages assume the project and the original game data are available
  const catalog = useCatalog().data
  const leagues = useOriginalLeagues().data
  const teams = useOriginalTeams().data
  const stadiums = useOriginalStadiums().data
  const ready = loaded && !!catalog && !!leagues && !!teams
  const counts: Record<string, number> = {
    '/leagues': draft.leagues.length,
    '/teams': draft.teams.length,
    '/players': draft.players.length,
    '/stadiums': stadiums?.length ?? 0,
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
          <p className="px-3 pt-2 text-xs text-muted-foreground">
            {t('app.credits')}{' '}
            <a href={AUTHOR_GITHUB} target="_blank" rel="noreferrer" className="underline-offset-2 hover:text-foreground hover:underline">
              {AUTHOR_NAME}
            </a>
            {' · '}
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="underline-offset-2 hover:text-foreground hover:underline">
              {t('app.sourceCode')}
            </a>
          </p>
        </div>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="z-10 flex shrink-0 justify-end border-b bg-background/95 px-6 py-3 backdrop-blur">
          <ProjectActions />
        </header>
        <GameWarnings />
        <main className="min-h-0 flex-1 overflow-auto p-6">
          {ready ? (
            <Outlet />
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
