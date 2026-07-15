import { dashboard as raw, encryptedSite as encryptedRaw } from 'virtual:jobscope-data'
import type { DashboardData, EncRef } from '@/lib/schema'

// dashboard.json is emitted by `jobscope dashboard --emit-json` and baked into
// the bundle at build time (no runtime fetch -> works offline from file://).
export const dashboard = raw as unknown as DashboardData

// Optional encrypted whole-site marker, injected only for a published build:
// either an inline EncBlob or a pointer to the lazily-fetched ciphertext.
export const encryptedSite = (encryptedRaw as EncRef | null) ?? null
