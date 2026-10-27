import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { en } from './en'
import { ptBR, type MessageKey } from './pt-BR'

export type { MessageKey }
export type Lang = 'pt-BR' | 'en'
export type Params = Record<string, unknown>
export type TFunction = (key: MessageKey, params?: Params) => string

export const LANGS: { value: Lang; label: string }[] = [
  { value: 'pt-BR', label: 'Português (Brasil)' },
  { value: 'en', label: 'English' },
]

const DICTIONARIES: Record<Lang, Record<MessageKey, string>> = { 'pt-BR': ptBR, en }
const STORAGE_KEY = 'fsmod.lang'

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'pt-BR' || saved === 'en') return saved
  } catch {
    /* storage blocked */
  }
  return navigator.language.toLowerCase().startsWith('pt') ? 'pt-BR' : 'en'
}

// module-level copy of the current language, for code that runs outside React (ApiError, plain helpers)
let currentLang: Lang = initialLang()

const format = (template: string, params?: Params) =>
  params
    ? template.replace(/\{(\w+)\}/g, (match, name: string) => {
        const value = params[name]
        if (value === undefined || value === null) return match
        return Array.isArray(value) ? value.join(', ') : String(value)
      })
    : template

export function hasMessage(key: string): key is MessageKey {
  return key in ptBR
}

/** Translation in the current language; also usable outside components (it does not re-render anything). */
export function translate(key: MessageKey, params?: Params): string {
  return format(DICTIONARIES[currentLang][key] ?? ptBR[key] ?? key, params)
}

interface I18nContextValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: TFunction
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(currentLang)
  const setLang = useCallback((next: Lang) => {
    currentLang = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* storage blocked: the choice lasts until the page reloads */
    }
    setLangState(next)
  }, [])
  useEffect(() => {
    document.documentElement.lang = lang
    document.title = translate('app.documentTitle')
  }, [lang])
  // a new `t` per language, so memoized code that depends on it recomputes
  const t = useCallback<TFunction>((key, params) => format(DICTIONARIES[lang][key] ?? ptBR[key] ?? key, params), [lang])
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n outside I18nProvider')
  return ctx
}
