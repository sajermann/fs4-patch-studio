import { Languages, Monitor, Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { LANGS, useI18n, type Lang } from '@/i18n'
import { useTheme } from '@/lib/theme'

const THEMES = [
  { value: 'light', key: 'prefs.themeLight', icon: Sun },
  { value: 'dark', key: 'prefs.themeDark', icon: Moon },
  { value: 'system', key: 'prefs.themeSystem', icon: Monitor },
] as const

/** Language and light/dark theme pickers (saved in the browser, not in the project). */
export function PreferencesMenu() {
  const { t, lang, setLang } = useI18n()
  const { theme, resolvedTheme, setTheme } = useTheme()
  const ThemeIcon = theme === 'system' ? Monitor : resolvedTheme === 'dark' ? Moon : Sun
  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={t('prefs.language')} title={t('prefs.language')}>
            <Languages />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>{t('prefs.language')}</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={lang} onValueChange={(v) => setLang(v as Lang)}>
            {LANGS.map((l) => (
              <DropdownMenuRadioItem key={l.value} value={l.value}>
                {l.label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={t('prefs.theme')} title={t('prefs.theme')}>
            <ThemeIcon />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>{t('prefs.theme')}</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
            {THEMES.map(({ value, key, icon: Icon }) => (
              <DropdownMenuRadioItem key={value} value={value}>
                <Icon /> {t(key)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
