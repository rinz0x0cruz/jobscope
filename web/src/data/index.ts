import raw from './dashboard.json'
import type { DashboardData } from '@/lib/schema'

// dashboard.json is emitted by `jobscope dashboard --emit-json` and baked into
// the bundle at build time (no runtime fetch -> works offline from file://).
export const dashboard = raw as unknown as DashboardData
