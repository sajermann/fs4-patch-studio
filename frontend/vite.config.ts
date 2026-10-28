import fs from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies the API to the FastAPI backend (backend, port 8765; FSMOD_API_PORT for a second backend,
// e.g. a sandbox with temporary folders while the real one runs).
const apiPort = process.env.FSMOD_API_PORT ?? '8765'
// the app version lives only in the desktop app config (also used by the release workflow)
const tauriConfig = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../desktop/src-tauri/tauri.conf.json'), 'utf-8'))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(tauriConfig.version) },
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { proxy: { '/api': `http://127.0.0.1:${apiPort}` } },
  // local app served from disk: one bundle is fine
  build: { chunkSizeWarningLimit: 1500 },
})
