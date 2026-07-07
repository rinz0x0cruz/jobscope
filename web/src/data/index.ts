import raw from './dashboard.json'
import type { DashboardData, EncRef } from '@/lib/schema'

// dashboard.json is emitted by `jobscope dashboard --emit-json` and baked into
// the bundle at build time (no runtime fetch -> works offline from file://).
export const dashboard = raw as unknown as DashboardData

// Optional encrypted whole-site marker, baked only for a published
// (`publish.ps1 -Encrypted`) build: either an inline EncBlob or a tiny pointer
// to the lazily-fetched ciphertext. import.meta.glob keeps the redacted public
// build and the local un-redacted build (no file) compiling.
const encModules = import.meta.glob<EncRef>('./applications.encrypted.json', {
  eager: true,
  import: 'default',
})
export const encryptedSite: EncRef | null =
  (Object.values(encModules)[0] as EncRef | undefined) ?? null
