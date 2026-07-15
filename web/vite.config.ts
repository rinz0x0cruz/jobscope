import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

const dataModuleId = 'virtual:jobscope-data'
const resolvedDataModuleId = `\0${dataModuleId}`

function resolveInput(envName: string, fallback: string): string | null {
  const configured = process.env[envName]
  if (configured === 'none') return null
  return path.resolve(configured || path.resolve(import.meta.dirname, fallback))
}

function readJson(pathname: string): unknown {
  return JSON.parse(readFileSync(pathname, 'utf8').replace(/^\uFEFF/, '')) as unknown
}

function jobscopeDataPlugin(): Plugin {
  return {
    name: 'jobscope-data',
    resolveId(id: string) {
      return id === dataModuleId ? resolvedDataModuleId : null
    },
    load(id: string) {
      if (id !== resolvedDataModuleId) return null
      const dashboardPath = resolveInput('JOBSCOPE_DASHBOARD_JSON', './src/data/dashboard.json')
      if (!dashboardPath || !existsSync(dashboardPath)) {
        throw new Error(`dashboard payload not found: ${dashboardPath || '<disabled>'}`)
      }
      this.addWatchFile(dashboardPath)
      const dashboard = readJson(dashboardPath)

      const encryptedPath = resolveInput(
        'JOBSCOPE_ENCRYPTED_JSON',
        './src/data/applications.encrypted.json',
      )
      let encryptedSite: unknown = null
      if (encryptedPath && existsSync(encryptedPath)) {
        this.addWatchFile(encryptedPath)
        encryptedSite = readJson(encryptedPath)
      }
      return `export const dashboard = ${JSON.stringify(dashboard)};\n` +
        `export const encryptedSite = ${JSON.stringify(encryptedSite)};\n`
    },
  }
}

// base: './' -> relative asset paths so the built app runs from both file://
// (offline) and the GitHub Pages subpath, per plan/ui-upgrade.md.
export default defineConfig({
  base: './',
  plugins: [
    jobscopeDataPlugin(),
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'jobscope',
        short_name: 'jobscope',
        description: 'Resume-driven job scout — ranked roles, enrichment, offline.',
        theme_color: '#0a0a0b',
        background_color: '#0a0a0b',
        display: 'standalone',
        start_url: './',
        scope: './',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        clientsClaim: true,
        skipWaiting: true,
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  build: {
    outDir: process.env.JOBSCOPE_BUILD_OUT_DIR || 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
  },
})
