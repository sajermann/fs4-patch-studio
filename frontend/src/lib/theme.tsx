import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark' | 'system'

// same key and rule as the inline script in index.html (it applies the class before the first paint)
const STORAGE_KEY = 'fsmod.theme'
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')

function savedTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved
  } catch {
    /* storage blocked */
  }
  return 'system'
}

interface ThemeContextValue {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: string) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

/** Light / dark / system theme: class "dark" on <html>, choice saved in the browser. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(savedTheme)
  const [systemDark, setSystemDark] = useState(darkQuery.matches)
  const resolvedTheme = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => {
    const onChange = () => setSystemDark(darkQuery.matches)
    darkQuery.addEventListener('change', onChange)
    return () => darkQuery.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', resolvedTheme === 'dark')
    root.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  const setTheme = useCallback((next: string) => {
    if (next !== 'light' && next !== 'dark' && next !== 'system') return
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* storage blocked: the choice lasts until the page reloads */
    }
    setThemeState(next)
  }, [])

  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}
