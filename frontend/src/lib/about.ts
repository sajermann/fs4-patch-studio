// App name and credits (a brand and a person's name: the same in every language, so not in the i18n dictionaries).
export const APP_NAME = 'FS4 Patch Studio'
export const AUTHOR_NAME = 'Bruno Sajermann'
export const AUTHOR_GITHUB = 'https://github.com/Sajermann'
export const REPO_URL = 'https://github.com/Sajermann/fs4-patch-studio'

declare const __APP_VERSION__: string // set by vite.config.ts from desktop/src-tauri/tauri.conf.json
export const APP_VERSION = __APP_VERSION__
