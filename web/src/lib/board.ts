// Board model for the v2 "cockpit" — the whole hunt as one Kanban pipeline.
// Pure derivation over the already-emitted dashboard payload (no change to the
// Python↔TS contract): tracked `applications` become stage cards, and the top
// un-applied `rows` seed the "New" column, so the board is the single source of
// truth for every role in flight. The columns ARE the funnel
// (new → prepared → applied → interview → offer/rejected).

import type { DashboardData, Tier } from '@/lib/schema'
import { STATUS_LABEL, statusColor } from '@/components/applications/constants'
import { staleness } from '@/lib/pipeline'

/** The pipeline stages rendered as board columns, left → right. `skipped` roles
 *  are intentionally excluded from the board. */
export type BoardStage = 'new' | 'prepared' | 'applied' | 'interview' | 'offer' | 'rejected'

export const BOARD_STAGES: readonly BoardStage[] = [
  'new',
  'prepared',
  'applied',
  'interview',
  'offer',
  'rejected',
] as const

/** A single role on the board — either a tracked application or an un-applied
 *  match seeded into the "New" column. */
export interface BoardCard {
  id: string // job_id (matches JobRow.id)
  company: string
  title: string
  stage: BoardStage
  kind: 'match' | 'application'
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
  /** Number of timeline emails on the application (0 for matches). */
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

/** How many top un-applied matches to seed into the "New" column. */
const NEW_MATCH_CAP = 40

function isClosedRow(status: string, closedAt: string): boolean {
  return (!!status && status !== 'open') || !!closedAt
}

/** Normalize a tracked application status onto a board stage (or null to drop it,
 *  e.g. `skipped`). Unknown statuses fall back to "New". */
function toStage(status: string): BoardStage | null {
  const s = (status || 'new').toLowerCase()
  if (s === 'skipped') return null
  if ((BOARD_STAGES as readonly string[]).includes(s)) return s as BoardStage
  return 'new'
}

/**
 * Build the Kanban columns from the dashboard payload. Applications are grouped
 * by their pipeline status; the remaining capacity of the "New" column is filled
 * with the highest-scoring un-applied, still-open matches. Follow-up staleness
 * (#27/#29) and ready HR outreach are surfaced as per-card flags.
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
  const appIds = new Set(apps.map((a) => a.job_id))

  const byStage = new Map<BoardStage, BoardCard[]>()
  for (const st of BOARD_STAGES) byStage.set(st, [])

  // 1) Tracked applications → their stage column.
  for (const app of apps) {
    const stage = toStage(app.status)
    if (!stage) continue
    const row = rowById.get(app.job_id)
    const dApplied = daysBetween(app.applied_at, now)
    byStage.get(stage)!.push({
      id: app.job_id,
      company: app.company,
      title: app.title,
      stage,
      kind: 'application',
      tier: row?.tier,
      score: row?.score,
      location: row?.location,
      appliedAt: app.applied_at || undefined,
      updatedAt: app.updated || undefined,
      daysSinceApplied: dApplied ?? undefined,
      followup: stale.get(app.job_id),
      outreach: outreachReady.has((app.company || '').toLowerCase()) || undefined,
      emails: (app.timeline ?? []).length,
      url: row?.url,
    })
  }

  // 2) Seed "New" with the best still-open matches we haven't applied to yet.
  const matches = rows
    .filter((r) => !appIds.has(r.id))
    .filter((r) => r.tier !== 'Skip')
    .filter((r) => !isClosedRow(r.status, r.closed_at))
    .sort((a, b) => b.score - a.score)
    .slice(0, NEW_MATCH_CAP)
  for (const r of matches) {
    byStage.get('new')!.push({
      id: r.id,
      company: r.company,
      title: r.title,
      stage: 'new',
      kind: 'match',
      tier: r.tier,
      score: r.score,
      location: r.location,
      outreach: outreachReady.has((r.company || '').toLowerCase()) || undefined,
      emails: 0,
      url: r.url,
    })
  }

  // Sort each column: applications by most-recently-updated, matches by score.
  for (const st of BOARD_STAGES) {
    byStage.get(st)!.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'application' ? -1 : 1
      if (a.kind === 'application')
        return (b.updatedAt ?? b.appliedAt ?? '').localeCompare(a.updatedAt ?? a.appliedAt ?? '')
      return (b.score ?? 0) - (a.score ?? 0)
    })
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
