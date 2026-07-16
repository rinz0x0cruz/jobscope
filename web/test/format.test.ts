import { describe, it, expect } from 'vitest'
import type { JobRow } from '@/lib/schema'
import { compLabel, compRatio, glassdoorRating, stockLabel, stockChange, daysAgo, fmtGenerated } from '@/lib/format'

const row = (p: unknown): JobRow => p as JobRow

// Feature: card labels (comp / stock) + relative dates shown across the UI.
describe('format: comp + stock labels', () => {
  it('compLabel prefers the enriched range, then salary, else null', () => {
    expect(compLabel(row({ enrich: { comp: { range: '$100k–$120k' } } }))).toBe('$100k–$120k')
    expect(compLabel(row({ enrich: {}, salary: '₹30L' }))).toBe('₹30L')
    expect(compLabel(row({ enrich: {} }))).toBeNull()
  })

  it('compRatio compares annualized posting and market midpoints conservatively', () => {
    expect(compRatio(row({
      salary_min: 110_000, salary_max: 130_000, salary_interval: 'year', currency: 'USD',
      enrich: { comp: { min: 90_000, max: 110_000, interval: 'year', currency: 'USD' } },
    }))).toBe(120)
    expect(compRatio(row({
      salary_min: 10_000, salary_max: 10_000, salary_interval: 'month', currency: 'USD',
      enrich: { comp: { min: 100_000, max: 100_000, interval: 'year', currency: 'USD' } },
    }))).toBe(120)
    expect(compRatio(row({
      salary_min: 100_000, salary_interval: 'year', currency: 'EUR',
      enrich: { comp: { min: 100_000, interval: 'year', currency: 'USD' } },
    }))).toBeNull()
  })

  it('reads a bounded Glassdoor rating', () => {
    expect(glassdoorRating(row({ enrich: { glassdoor: { rating: 4.2 } } }))).toBe(4.2)
    expect(glassdoorRating(row({ enrich: { glassdoor: { rating: '4.2' } } }))).toBeNull()
  })

  it('stockLabel formats ticker · market cap, or "Not public"', () => {
    expect(stockLabel(row({ enrich: { stock: { ticker: 'ACME', market_cap: '$1B' } } }))).toBe('ACME · $1B')
    expect(stockLabel(row({ enrich: { stock: { ticker: 'ZZZ' } } }))).toBe('ZZZ')
    expect(stockLabel(row({ enrich: { stock: { public: false } } }))).toBe('Not public')
    expect(stockLabel(row({ enrich: {} }))).toBeNull()
  })

  it('stockChange returns the numeric change or null', () => {
    expect(stockChange(row({ enrich: { stock: { change_pct: -2.5 } } }))).toBe(-2.5)
    expect(stockChange(row({ enrich: {} }))).toBeNull()
  })
})

describe('format: dates', () => {
  it('daysAgo floors whole days and rejects bad input', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString()
    expect(daysAgo(twoDaysAgo)).toBe(2)
    expect(daysAgo(null)).toBeNull()
    expect(daysAgo('not-a-date')).toBeNull()
  })

  it('fmtGenerated echoes an unparseable string and formats a valid one', () => {
    expect(fmtGenerated('nonsense')).toBe('nonsense')
    const formatted = fmtGenerated('2026-07-06T11:06:57Z')
    expect(formatted).not.toBe('2026-07-06T11:06:57Z')
    expect(formatted.length).toBeGreaterThan(0)
  })
})
