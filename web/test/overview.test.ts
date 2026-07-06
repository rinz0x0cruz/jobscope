import { describe, it, expect } from 'vitest'
import type { JobRow } from '@/lib/schema'
import { tierSegments, topCompanies, funnelBars, topMatches } from '@/lib/overview'

const row = (p: unknown): JobRow => p as JobRow

// Feature: Overview -> "Fit distribution" donut + the bar cards.
describe('overview: fit distribution (donut segments)', () => {
  it('counts tiers, omits empty ones, and gives cumulative offsets', () => {
    const rows = [
      row({ tier: 'Strong' }),
      row({ tier: 'Good' }),
      row({ tier: 'Good' }),
      row({ tier: 'Skip' }),
    ]
    const { segs, total } = tierSegments(rows)
    expect(total).toBe(4)

    const byLabel = Object.fromEntries(segs.map((s) => [s.label, s]))
    expect(byLabel.Strong.value).toBe(1)
    expect(byLabel.Good.value).toBe(2)
    expect(byLabel.Skip.value).toBe(1)
    expect('Stretch' in byLabel).toBe(false) // zero-count tier is dropped

    expect(segs[0].start).toBe(0)
    expect(segs.reduce((n, s) => n + s.fraction, 0)).toBeCloseTo(1)
  })

  it('never divides by zero on an empty set', () => {
    const { segs, total } = tierSegments([])
    expect(total).toBe(0)
    expect(segs).toEqual([])
  })
})

describe('overview: bar + match cards', () => {
  it('ranks top companies by count (capped)', () => {
    const rows = [row({ company: 'Acme' }), row({ company: 'Acme' }), row({ company: 'Beta' })]
    expect(topCompanies(rows, 2)).toEqual([
      { label: 'Acme', value: 2 },
      { label: 'Beta', value: 1 },
    ])
  })

  it('orders funnel bars by pipeline stage, not by count', () => {
    const bars = funnelBars({ rejected: 2, applied: 5, offer: 1 })
    expect(bars.map((b) => b.label)).toEqual(['applied', 'offer', 'rejected'])
  })

  it('returns the highest-scoring matches first', () => {
    const rows = [row({ score: 10 }), row({ score: 90 }), row({ score: 50 })]
    expect(topMatches(rows, 2).map((r) => r.score)).toEqual([90, 50])
  })
})
