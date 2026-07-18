import { dashboard as raw, encryptedSite as encryptedRaw } from 'virtual:jobscope-data'
import { normalizeDashboardData, type DashboardData, type EncRef } from '@/lib/schema'

// dashboard.json is a startup fallback for local/dev builds. `jobscope serve`
// replaces it at runtime from SQLite; static Pages unlocks encryptedSite instead.
export const dashboard = normalizeDashboardData(raw as unknown as DashboardData)

// Optional encrypted whole-site marker, injected only for a published build:
// either an inline EncBlob or a pointer to the lazily-fetched ciphertext.
export const encryptedSite = (encryptedRaw as EncRef | null) ?? null
