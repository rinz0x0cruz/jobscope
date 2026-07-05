import raw from './dashboard.json'
import type { DashboardData, EncBlob } from '@/lib/schema'

// dashboard.json is emitted by `jobscope dashboard --emit-json` and baked into
// the bundle at build time (no runtime fetch -> works offline from file://).
export const dashboard = raw as unknown as DashboardData

// Optional AES-256-GCM applications blob, baked in only for an encrypted
// (`publish.ps1 -Encrypted`) build. Loaded via import.meta.glob so the redacted
// public build and the local un-redacted build (no blob file) still compile.
const encModules = import.meta.glob<EncBlob>('./applications.encrypted.json', {
  eager: true,
  import: 'default',
})
export const encryptedApplications: EncBlob | null =
  (Object.values(encModules)[0] as EncBlob | undefined) ?? null
