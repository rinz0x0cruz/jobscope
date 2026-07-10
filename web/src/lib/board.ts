// Board model for the v2 cockpit — the APPLIED pipeline. Pure derivation over the
// emitted `applications`: each tracked application becomes a card in its stage
// column (applied → interview → offer → rejected). Un-applied matches live in the
// separate "To apply" list, not here. Follow-up staleness (#27/#29) and ready HR
// outreach surface as per-card flags.

import type { DashboardData, Tier } from '@/lib/schema'
import { STATUS_LABEL, statusColor } from '@/components/applications/constants'
import { staleness } from '@/lib/pipeline'

/** The pipeline stages rendered as board columns, left → right. Roles that
 *  haven't been submitted (new / prepared) and skipped roles are not on the
 *  board — un-applied matches live in the "To apply" list. */
export type BoardStage = 'applied' | 'interview' | 'offer' | 'rejected'

export const BOARD_STAGES: readonly BoardStage[] = [
  'applied',
  'interview',
  'offer',
  'rejected',
] as const

/** A single applied role on the board. */
export interface BoardCard {
  id: string // job_id (matches JobRow.id)
  company: string
  title: string
  stage: BoardStage
  tier?: Tier
  score?: number
  location?: string
  appliedAt?: string
  updatedAt?: string
  daysSinceApplied?: number
  /** Set when an applied role has gone quiet: due for a nudge, or likely ghosted. */
  followup?: 'due' | 'ghosted'
  /** True when the company has HR contacts ready to reach out to. */
  outreach?: boolean
  /** Number of timeline emails on the application. */
  emails?: number
  url?: string
}

export interface BoardColumn {
  stage: BoardStage
  label: string
  /** Accent color for the column header / card rail (shared with the funnel). */
  color: string
  cards: BoardCard[]
}

/** Normalize a tracked application status onto a board stage, or null to drop it:
 *  new / prepared (not yet submitted → the "To apply" list) and skipped (hidden). */
function toStage(status: string): BoardStage | null {
  const s = (status || '').toLowerCase()
  return (BOARD_STAGES as readonly string[]).includes(s) ? (s as BoardStage) : null
}

/**
 * Build the Kanban columns from the dashboard payload: tracked applications
 * grouped by pipeline status (applied → interview → offer → rejected). Follow-up
 * staleness (#27/#29) and ready HR outreach are surfaced as per-card flags.
 */
export function buildBoard(data: DashboardData, now = Date.now()): BoardColumn[] {
  const apps = data.applications ?? []
  const rows = data.rows ?? []

  // job_id → follow-up bucket, for applications that have gone quiet.
  const stale = new Map<string, 'due' | 'ghosted'>()
  for (const s of staleness(apps, now)) {
    if (s.bucket === 'due' || s.bucket === 'ghosted') stale.set(s.app.job_id, s.bucket)
  }

  // Companies (lower-cased) with at least one ready HR contact.
  const outreachReady = new Set(
    (data.applied_outreach ?? [])
      .filter((c) => (c.contacts ?? []).length > 0)
      .map((c) => c.company.toLowerCase()),
  )

  // Fast lookups from the un-redacted rows for tier/score/location/url.
  const rowById = new Map(rows.map((r) => [r.id, r]))

  const byStage = new Map<BoardStage, BoardCard[]>()
  for (const st of BOARD_STAGES) byStage.set(st, [])

  for (const app of apps) {
    const stage = toStage(app.status)
    if (!stage) continue
    const row = rowById.get(app.job_id)
    byStage.get(stage)!.push({
      id: app.job_id,
      company: app.company,
      title: app.title,
      stage,
      tier: row?.tier,
      score: row?.score,
      location: row?.location,
      appliedAt: app.applied_at || undefined,
      updatedAt: app.updated || undefined,
      daysSinceApplied: daysBetween(app.applied_at, now) ?? undefined,
      followup: stale.get(app.job_id),
      outreach: outreachReady.has((app.company || '').toLowerCase()) || undefined,
      emails: (app.timeline ?? []).length,
      url: row?.url,
    })
  }

  // Most-recently-updated first within each stage.
  for (const st of BOARD_STAGES) {
    byStage.get(st)!.sort((a, b) =>
      (b.updatedAt ?? b.appliedAt ?? '').localeCompare(a.updatedAt ?? a.appliedAt ?? ''),
    )
  }

  return BOARD_STAGES.map((stage) => ({
    stage,
    label: STATUS_LABEL[stage] ?? stage,
    color: statusColor(stage),
    cards: byStage.get(stage)!,
  }))
}

/** Case-insensitive substring filter across company / title / location, applied
 *  to every column (empty query returns the columns unchanged). */
export function filterBoard(columns: BoardColumn[], query: string): BoardColumn[] {
  const q = query.trim().toLowerCase()
  if (!q) return columns
  return columns.map((col) => ({
    ...col,
    cards: col.cards.filter((c) =>
      `${c.company} ${c.title} ${c.location ?? ''}`.toLowerCase().includes(q),
    ),
  }))
}

function daysBetween(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : Math.floor((now - t) / 86_400_000)
}
