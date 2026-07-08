import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FacetBar } from '@/components/filters/FacetBar'
import { FACET_KEYS, type FacetKey } from '@/lib/urlState'
import type { FacetOption } from '@/lib/filters'

const emptyByKey = <T,>(v: () => T) =>
  Object.fromEntries(FACET_KEYS.map((k) => [k, v()])) as Record<FacetKey, T>

function renderBar(overrides: Partial<Record<FacetKey, FacetOption[]>> = {}) {
  const options = { ...emptyByKey<FacetOption[]>(() => []), ...overrides }
  render(
    <FacetBar
      options={options}
      selected={emptyByKey<string[]>(() => [])}
      onToggle={() => {}}
      group={false}
      onGroup={() => {}}
      hideClosed={false}
      onHideClosed={() => {}}
      activeCount={0}
      onClear={() => {}}
    />,
  )
}

describe('FacetBar: Resume facet hint (#10)', () => {
  const HINT = 'Import 2+ named resumes and rerun match to filter by resume'

  it('shows a disabled Resume facet with guidance when there are <2 resume bases', () => {
    renderBar()
    expect(screen.getByTitle(HINT)).toBeDisabled()
  })

  it('drops the hint once 2+ resume bases exist (a real facet renders instead)', () => {
    renderBar({
      resume: [
        { value: 'research', count: 3 },
        { value: 'consulting', count: 2 },
      ] as unknown as FacetOption[],
    })
    expect(screen.queryByTitle(HINT)).toBeNull()
  })
})
