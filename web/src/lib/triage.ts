// "To apply" model for the v2 cockpit — the roles you can still apply to: fresh,
// un-applied, still-open matches ordered by fit. Pure derivation; the surface
// renders them as a ranked, tier-grouped list with progressive "show more".

import type { DashboardData, Tier } from '@/lib/schema'
import { daysSince } from '@/lib/pipeline'

export interface TriageItem {
  jobId: string
  company: string
  title: string
  tier: Tier
  score: number
  location: string
  remote: boolean
  ageDays: number | null
  /** Posted-date age; likely-stale/ghost when `stale` is set (see filters.stale_days). */
  postedAgeDays: number | null
  stale: boolean
  /** Tagged remote but the JD reads onsite/hybrid (see render._remote_mismatch). */
  remoteMismatch: boolean
  /** Distinct source names this role appears under (>1 = cross-source duplicate). */
  sources: string[]
  /** One-line reason this surfaced (rationale/brief), for a quick decision. */
  brief: string
  url: string
}

export interface TriageQueue {
  items: TriageItem[]
  total: number
}

/** Build the review queue: the highest-fit roles you have not applied to yet
 *  (open, non-Skip), newest-strong first. */
export function buildTriage(data: DashboardData, now = Date.now(), cap = 60): TriageQueue {
  const apps = data.applications ?? []
  const rows = data.rows ?? []
  const appIds = new Set(apps.map((a) => a.job_id))

  const items = rows
    .filter((r) => !appIds.has(r.id))
    .filter((r) => r.tier !== 'Skip' && r.status === 'open' && !r.closed_at)
    .sort((a, b) => b.score - a.score)
    .slice(0, cap)
    .map<TriageItem>((r) => ({
      jobId: r.id,
      company: r.company,
      title: r.title,
      tier: r.tier,
      score: r.score,
      location: r.location,
      remote: r.remote,
      ageDays: daysSince(r.first_seen, now),
      postedAgeDays: r.posted_age_days,
      stale: r.stale,
      remoteMismatch: r.remote_mismatch,
      sources: [...new Set(r.sources.map((s) => s.source))],
      brief: (r.brief || r.rationale || '').trim(),
      url: r.url,
    }))

  return { items, total: items.length }
}

/** Case-insensitive filter across company / title / location (empty query returns
 *  the queue unchanged). */
export function filterTriage(queue: TriageQueue, query: string): TriageQueue {
  const q = query.trim().toLowerCase()
  if (!q) return queue
  const items = queue.items.filter((i) =>
    `${i.company} ${i.title} ${i.location}`.toLowerCase().includes(q),
  )
  return { items, total: items.length }
}
