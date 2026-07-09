// Triage model for the v2 cockpit — a keyboard-first "today's queue" of the
// decisions worth making now: fresh, un-applied, still-open matches ordered by
// fit. Pure derivation; the surface walks the queue one card at a time.

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
      brief: (r.brief || r.rationale || '').trim(),
      url: r.url,
    }))

  return { items, total: items.length }
}
