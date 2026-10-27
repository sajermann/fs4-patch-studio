# Frontend

React + Vite + TypeScript + Tailwind + shadcn/ui. Code is English; the UI is translated (pt-BR and English).

- **Languages** (`src/i18n/`): flat dictionaries `pt-BR.ts` (the reference) and `en.ts` (typed: a missing key fails
  `tsc`). Components use `const { t } = useI18n()` and `t('key', { param })`; code outside React uses `translate()`.
  `rich()` renders `` `code` `` and `**bold**` inside long texts. Backend messages are translated by their `code`
  (validation issues: `issue.<code>` with the issue params, `lib/issues.ts`; HTTP errors: `apiError.<code>`, in
  `ApiError`), falling back to the backend's pt-BR text. The choice is saved in the browser (`fsmod.lang`); default
  = the browser language. New language: add a dictionary and an entry in `LANGS`.
- **Theme** (`src/lib/theme.tsx`): light / dark / system, class `dark` on `<html>`, saved in `fsmod.theme`; the inline
  script in `index.html` applies it before the first paint. Both pickers are in `components/layout/PreferencesMenu.tsx`
  (sidebar footer and the setup screen).

- `npm run dev` — dev server on http://localhost:5173 (proxies `/api` to the backend on port 8765, which must be running:
  `python -m fsapi --no-browser` in `app/backend`).
- `npm run build` — builds `dist/`, served by the backend at `/` (`app\start.bat` builds it on first run).

Structure: `src/api` (types mirroring contract v2 + fetch client), `src/state` (project draft, live validation,
React Query hooks), `src/components/layout` (shell, save / build patch / install), `src/components/common`
(form helpers), `src/pages` (Ligas, Times, Jogadores, Configuração).

The project is edited as a draft in memory: "Salvar" (Ctrl+S) writes `database.json`; "Gerar patch" saves and builds
`app/backend/patch`; validation runs on the backend (`POST /api/project/validate`) while editing.
