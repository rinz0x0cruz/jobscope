import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PrimaryNav, primaryFor } from '@/components/PrimaryNav'
import { TierSegment } from '@/components/TierSegment'
import type { TabValue } from '@/lib/urlState'

const counts: Record<TabValue, number> = {
  overview: 0, applications: 3, all: 127, Strong: 1, Good: 9, Stretch: 16, Skip: 101,
}

describe('primaryFor', () => {
  it('maps every tab to a primary (tier buckets -> jobs)', () => {
    expect(primaryFor('overview')).toBe('overview')
    expect(primaryFor('applications')).toBe('applications')
    for (const t of ['all', 'Strong', 'Good', 'Stretch', 'Skip'] as TabValue[]) {
      expect(primaryFor(t)).toBe('jobs')
    }
  })
})

describe('PrimaryNav', () => {
  it('renders 3 destinations and marks the active primary (a tier -> Jobs)', () => {
    render(<PrimaryNav tab="Strong" jobsCount={127} appsCount={3} onSelect={() => {}} />)
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    expect(screen.getByRole('tab', { name: /Jobs/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /Overview/ })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByText('127')).toBeInTheDocument() // jobs count
    expect(screen.getByText('3')).toBeInTheDocument() // apps count
  })

  it('fires onSelect("jobs") when Jobs is chosen', () => {
    const onSelect = vi.fn()
    render(<PrimaryNav tab="overview" jobsCount={5} appsCount={0} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('tab', { name: /Jobs/ }))
    expect(onSelect).toHaveBeenCalledWith('jobs')
  })
})

describe('TierSegment', () => {
  it('renders 5 tier radios and checks the active one', () => {
    const onChange = vi.fn()
    render(<TierSegment value="Good" counts={counts} onChange={onChange} />)
    expect(screen.getAllByRole('radio')).toHaveLength(5)
    expect(screen.getByRole('radio', { name: /Good/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /All/ })).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(screen.getByRole('radio', { name: /Strong/ }))
    expect(onChange).toHaveBeenCalledWith('Strong')
  })
})
