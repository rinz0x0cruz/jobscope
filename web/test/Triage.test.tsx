import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Triage } from '@/features/triage'
import type { TriageItem, TriageQueue } from '@/lib/triage'

function item(over: Partial<TriageItem> & Pick<TriageItem, 'jobId'>): TriageItem {
  return {
    company: 'Acme',
    title: 'Engineer',
    tier: 'Good',
    score: 60,
    location: 'Remote',
    remote: true,
    ageDays: 1,
    postedAgeDays: null,
    stale: false,
    remoteMismatch: false,
    sources: [],
    salary: '',
    hasReferral: false,
    coveragePct: null,
    brief: '',
    url: 'https://x',
    ...over,
  }
}

const queue = (items: TriageItem[]): TriageQueue => ({ items, total: items.length })

describe('Triage (To apply list)', () => {
  it('renders ranked rows with tier group landmarks', () => {
    render(
      <Triage
        queue={queue([
          item({ jobId: 'a', company: 'Stripe', tier: 'Strong', score: 90 }),
          item({ jobId: 'b', company: 'Globex', tier: 'Good', score: 60 }),
        ])}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Stripe')).toBeInTheDocument()
    expect(screen.getByText('Globex')).toBeInTheDocument()
    // tier appears as both a group header and a per-row chip
    expect(screen.getAllByText('Strong').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Good').length).toBeGreaterThan(0)
  })

  it('opens a role when its row is clicked', () => {
    const onOpen = vi.fn()
    render(
      <Triage
        queue={queue([item({ jobId: 'j1', company: 'Stripe', title: 'Backend Engineer' })])}
        onOpen={onOpen}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Stripe — Backend Engineer' }))
    expect(onOpen).toHaveBeenCalledWith('j1')
  })

  it('reveals more rows with the Show more button', () => {
    const items = Array.from({ length: 20 }, (_, i) => item({ jobId: `j${i}`, company: `Co${i}` }))
    render(<Triage queue={queue(items)} onOpen={() => {}} />)
    expect(screen.getByText('Co0')).toBeInTheDocument()
    expect(screen.queryByText('Co18')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Show \d+ more/ }))
    expect(screen.getByText('Co18')).toBeInTheDocument()
  })

  it('filters live by the query prop', () => {
    render(
      <Triage
        query="stripe"
        queue={queue([
          item({ jobId: 'a', company: 'Stripe' }),
          item({ jobId: 'b', company: 'Globex' }),
        ])}
        onOpen={() => {}}
      />,
    )
    expect(screen.getByText('Stripe')).toBeInTheDocument()
    expect(screen.queryByText('Globex')).not.toBeInTheDocument()
  })

  it('shows an empty state when there is nothing to apply to', () => {
    render(<Triage queue={queue([])} onOpen={() => {}} />)
    expect(screen.getByText(/No new roles to apply to/i)).toBeInTheDocument()
  })
})
