// Overview model for the v2 cockpit — a chart-first "state of the hunt" derived
// purely from the emitted payload (no contract change). Turns the raw pipeline
// into KPI figures, a fit-tier donut, a conversion funnel, top-N breakdowns, a
// weekly surfacing trend, and a score histogram.

import type { Application, DashboardData, JobRow, Tier } from '@/lib/schema'
import { TIERS, TIER_COLOR } from '@/lib/schema'

export interface DonutSeg {
  label: string
  value: number
  color: string
  fraction: number
  /** Cumulative start offset (0–1) for stroke-dashoffset placement. */
  start: number
}

export interface BarItem {
  label: string
  value: number
  color?: string
}

export interface FunnelStage {
  key: string
  label: string
  value: number
  /** Width fraction (0–1) relative to the first (widest) stage. */
  fraction: number
  color: string
}

export interface TrendPoint {
  label: string
  value: number
}

export interface Kpi {
  key: string
  label: string
  value: number
}

export interface OverviewModel {
  kpis: Kpi[]
  tiers: { segs: DonutSeg[]; total: number }
  funnel: FunnelStage[]
  companies: BarItem[]
  locations: BarItem[]
  sources: BarItem[]
  trend: TrendPoint[]
  scores: BarItem[]
  hasRoles: boolean
  hasApplications: boolean
}

const WEEK_MS = 7 * 24 * 60 * 60 * 1000

function parseTime(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : t
}

function tierCounts(rows: JobRow[]): Record<Tier, number> {
  const counts: Record<Tier, number> = { Strong: 0, Good: 0, Stretch: 0, Skip: 0 }
  for (const r of rows) counts[r.tier] = (counts[r.tier] ?? 0) + 1
  return counts
}

function tierDonut(rows: JobRow[]): { segs: DonutSeg[]; total: number } {
  const counts = tierCounts(rows)
  const total = rows.length || 1
  let start = 0
  const segs: DonutSeg[] = []
  for (const t of TIERS) {
    const value = counts[t]
    if (value <= 0) continue
    const fraction = value / total
    segs.push({ label: t, value, color: TIER_COLOR[t], fraction, start })
    start += fraction
  }
  return { segs, total: rows.length }
}

function topBy(rows: JobRow[], pick: (r: JobRow) => string, n = 8): BarItem[] {
  const m = new Map<string, number>()
  for (const r of rows) {
    const key = (pick(r) || '').trim()
    if (!key) continue
    m.set(key, (m.get(key) ?? 0) + 1)
  }
  return [...m.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
    .slice(0, n)
}

const INTERVIEW_SIGNALS = new Set(['interview', 'assessment'])

function reachedInterview(a: Application): boolean {
  if (a.status === 'interview' || a.status === 'offer') return true
  return (a.timeline ?? []).some((e) => INTERVIEW_SIGNALS.has(e.signal))
}

function reachedOffer(a: Application): boolean {
  if (a.status === 'offer') return true
  return (a.timeline ?? []).some((e) => e.signal === 'offer')
}

// A monotonic application funnel: every app is "applied", interviews are a subset
// (an offer implies an interview), and offers a subset of interviews. Kept apart
// from the fit tiers (a different universe: apps can outnumber tracked rows).
function buildFunnel(apps: Application[]): FunnelStage[] {
  const interview = apps.filter((a) => reachedInterview(a) || reachedOffer(a)).length
  const stages = [
    { key: 'applied', label: 'Applied', value: apps.length, color: 'var(--brand-coral)' },
    { key: 'interview', label: 'Interview', value: interview, color: 'var(--stretch)' },
    { key: 'offer', label: 'Offer', value: apps.filter(reachedOffer).length, color: 'var(--strong)' },
  ]
  const top = Math.max(1, stages[0].value)
  return stages.map((s) => ({ ...s, fraction: s.value / top }))
}

function buildTrend(rows: JobRow[], now: number, weeks = 8): TrendPoint[] {
  const points: TrendPoint[] = []
  for (let i = weeks - 1; i >= 0; i--) {
    const end = now - i * WEEK_MS
    const start = end - WEEK_MS
    const value = rows.filter((r) => {
      const t = parseTime(r.first_seen)
      return t !== null && t > start && t <= end
    }).length
    const d = new Date(end)
    points.push({ label: `${d.getMonth() + 1}/${d.getDate()}`, value })
  }
  return points
}

const SCORE_BANDS: { label: string; min: number; max: number; color: string }[] = [
  { label: '<60', min: -Infinity, max: 60, color: 'var(--skip)' },
  { label: '60-69', min: 60, max: 70, color: 'var(--stretch)' },
  { label: '70-79', min: 70, max: 80, color: 'var(--good)' },
  { label: '80-89', min: 80, max: 90, color: 'var(--good)' },
  { label: '90+', min: 90, max: Infinity, color: 'var(--strong)' },
]

function buildScores(rows: JobRow[]): BarItem[] {
  return SCORE_BANDS.map((b) => ({
    label: b.label,
    color: b.color,
    value: rows.filter((r) => r.score >= b.min && r.score < b.max).length,
  }))
}

export function buildOverview(data: DashboardData, now = Date.now()): OverviewModel {
  const rows = data.rows ?? []
  const apps = data.applications ?? []
  const counts = tierCounts(rows)
  const interviews = apps.filter(reachedInterview).length
  const offers = apps.filter(reachedOffer).length
  const avgFit = rows.length
    ? Math.round(rows.reduce((sum, r) => sum + (r.score || 0), 0) / rows.length)
    : 0

  const kpis: Kpi[] = [
    { key: 'roles', label: 'Roles tracked', value: data.total || rows.length },
    { key: 'strong', label: 'Strong fits', value: counts.Strong },
    { key: 'applied', label: 'Applications', value: apps.length },
    { key: 'interviews', label: 'Interviews', value: interviews },
    { key: 'offers', label: 'Offers', value: offers },
    { key: 'avgfit', label: 'Avg fit', value: avgFit },
  ]

  return {
    kpis,
    tiers: tierDonut(rows),
    funnel: buildFunnel(apps),
    companies: topBy(rows, (r) => r.company),
    locations: topBy(rows, (r) => (r.remote ? 'Remote' : r.location || r.place)),
    sources: topBy(rows, (r) => r.source),
    trend: buildTrend(rows, now),
    scores: buildScores(rows),
    hasRoles: rows.length > 0,
    hasApplications: apps.length > 0,
  }
}
