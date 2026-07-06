import { describe, it, expect } from 'vitest'
import { searchSchema, SEARCH_DEFAULTS, TAB_VALUES, FACET_KEYS } from '@/lib/urlState'

// Feature: shareable URL view-state (tabs, search, facets) with safe fallbacks.
describe('urlState: schema + defaults', () => {
  it('falls back to safe defaults on empty input', () => {
    const s = searchSchema.parse({})
    expect(s.tab).toBe('all')
    expect(s.q).toBe('')
    expect(s.group).toBe(false)
    expect(s.hideClosed).toBe(true)
    expect(s.resume).toEqual([])
  })

  it('coerces an invalid tab to "all" instead of throwing', () => {
    expect(searchSchema.parse({ tab: 'bogus' }).tab).toBe('all')
  })

  it('preserves valid values', () => {
    const s = searchSchema.parse({ tab: 'Strong', q: 'siem', country: ['India'], group: true })
    expect(s.tab).toBe('Strong')
    expect(s.q).toBe('siem')
    expect(s.country).toEqual(['India'])
    expect(s.group).toBe(true)
  })

  it('exposes the tabs + facet keys the UI relies on', () => {
    expect(FACET_KEYS).toEqual(['resume', 'country', 'place', 'mode', 'funding', 'scope'])
    expect(TAB_VALUES).toContain('applications')
    expect(TAB_VALUES).toContain('overview')
    expect(SEARCH_DEFAULTS.hideClosed).toBe(true)
  })
})
