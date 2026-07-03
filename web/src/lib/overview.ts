import type { JobRow, Tier } from './schema'
import { TIERS, TIER_COLOR } from './schema'

export interface Seg {
  label: string
  value: number
  color: string
  fraction: number
  start: number
}

/** Donut segments for the tier (fit) distribution, with cumulative start offsets. */
export function tierSegments(rows: JobRow[]): { segs: Seg[]; total: number } {
  const counts: Record<Tier, number> = { Strong: 0, Good: 0, Stretch: 0, Skip: 0 }
  for (const r of rows) counts[r.tier] += 1
  const total = rows.length || 1
  let start = 0
  const segs: Seg[] = []
  for (const t of TIERS) {
    const value = counts[t]
    if (value <= 0) continue
    const fraction = value / total
    segs.push({ label: t, value, color: TIER_COLOR[t], fraction, start })
    start += fraction
  }
  return { segs, total: rows.length }
}

export interface BarItem {
  label: string
  value: number
}

export function topCompanies(rows: JobRow[], n = 8): BarItem[] {
  const m = new Map<string, number>()
  for (const r of rows) {
    const c = r.company || '—'
    m.set(c, (m.get(c) ?? 0) + 1)
  }
  return [...m.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, n)
}

const FUNNEL_ORDER = ['new', 'applied', 'interview', 'offer', 'rejected', 'closed']

export function funnelBars(funnel: Record<string, number>): BarItem[] {
  return Object.entries(funnel)
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => {
      const ia = FUNNEL_ORDER.indexOf(a.label)
      const ib = FUNNEL_ORDER.indexOf(b.label)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
}

/** Highest-scoring roles for the Top matches table. */
export function topMatches(rows: JobRow[], n = 25): JobRow[] {
  return [...rows].sort((a, b) => b.score - a.score).slice(0, n)
}
