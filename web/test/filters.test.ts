import { describe, it, expect } from 'vitest'
import type { JobRow } from '@/lib/schema'
import type { SearchState } from '@/lib/urlState'
import { SEARCH_DEFAULTS } from '@/lib/urlState'
import { tabPool, applyFacets, facetOptions, toggleValue, countActive, isClosed } from '@/lib/filters'

const row = (p: unknown): JobRow => p as JobRow
const state = (p: Partial<SearchState> = {}): SearchState =>
  ({ ...SEARCH_DEFAULTS, job: undefined, ...p }) as SearchState

// Feature: faceted filtering + tier tabs + hide-closed.
describe('filters: toggles + closed detection', () => {
  it('toggleValue adds then removes immutably', () => {
    expect(toggleValue([], 'India')).toEqual(['India'])
    expect(toggleValue(['India'], 'India')).toEqual([])
    const before = ['India']
    toggleValue(before, 'US')
    expect(before).toEqual(['India']) // original array untouched
  })

  it('isClosed detects non-open status or a closed_at date', () => {
    expect(isClosed(row({ status: 'closed' }))).toBe(true)
    expect(isClosed(row({ closed_at: '2026-07-01' }))).toBe(true)
    expect(isClosed(row({ status: 'open' }))).toBe(false)
  })
})

describe('filters: tab pool + facets', () => {
  it('tabPool filters by tier and hides closed roles', () => {
    const rows = [
      row({ tier: 'Strong', status: 'open' }),
      row({ tier: 'Good', status: 'open' }),
      row({ tier: 'Strong', status: 'closed' }),
    ]
    expect(tabPool(rows, 'Strong', true)).toHaveLength(1)
    expect(tabPool(rows, 'Strong', false)).toHaveLength(2)
    expect(tabPool(rows, 'all', true)).toHaveLength(2)
  })

  it('applyFacets keeps only rows matching the selected facet values', () => {
    const rows = [
      row({ base: 'sec', country: 'India', place: 'Remote', remote: true, funding: 'Public', remote_scope: 'Anywhere' }),
      row({ base: 'sec', country: 'US', place: 'NYC', remote: false, funding: 'Public', remote_scope: '' }),
    ]
    expect(applyFacets(rows, state({ country: ['India'] }))).toHaveLength(1)
    expect(applyFacets(rows, state())).toHaveLength(2) // nothing selected -> all pass
  })

  it('facetOptions counts values (highest first)', () => {
    const mk = (country: string, place: string) =>
      row({ base: 'a', country, place, remote: true, funding: 'Public', remote_scope: 'Anywhere' })
    const rows = [mk('India', 'X'), mk('India', 'Y'), mk('US', 'Z')]
    expect(facetOptions(rows, state(), 'country')).toEqual([
      { value: 'India', count: 2 },
      { value: 'US', count: 1 },
    ])
  })

  it('countActive sums every selected facet value', () => {
    expect(countActive(state({ country: ['India'], place: ['Remote', 'NYC'] }))).toBe(3)
    expect(countActive(state())).toBe(0)
  })
})
