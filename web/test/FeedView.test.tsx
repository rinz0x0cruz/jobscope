import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { FeedView } from '@/features/feed'
import { buildFeed } from '@/lib/feed'
import { searchSchema } from '@/lib/urlState'
import { dashboard, jobRow } from './factories'

const data = dashboard({
  rows: [
    jobRow({
      id: 'strong',
      company: 'Stripe',
      title: 'Security Engineer',
      tier: 'Strong',
      score: 92,
      salary: '$180k',
      rationale: 'top: skills 100%, location 85%, recency 70% | skills matched: python, aws',
    }),
    jobRow({ id: 'good', company: 'Globex', title: 'Detection Engineer', tier: 'Good', score: 72, remote: false }),
  ],
})

function setup(over: Record<string, unknown> = {}) {
  const state = searchSchema.parse(over)
  const model = buildFeed(data, state)
  const onSelect = vi.fn()
  const onStateChange = vi.fn()
  const view = render(
    <FeedView
      model={model}
      state={state}
      onSelect={onSelect}
      onStateChange={onStateChange}
    />,
  )
  return { ...view, model, onSelect, onStateChange, state }
}

describe('FeedView', () => {
  it('renders ranked role metadata and opens a selection', () => {
    const { onSelect } = setup()
    expect(screen.getByText('Stripe')).toBeInTheDocument()
    expect(screen.getByText('$180k')).toBeInTheDocument()
    expect(screen.getByText('Skills')).toBeInTheDocument()
    expect(screen.getByText('python · aws')).toBeInTheDocument()
    expect(screen.queryByText(/top: skills/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stripe — Security Engineer' }))
    expect(onSelect).toHaveBeenCalledWith('strong')
  })

  it('updates quick filters and sort state', () => {
    const { onStateChange } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Quick filter: Remote' }))
    expect(onStateChange).toHaveBeenCalledWith({ flags: ['remote'] }, { replace: true })
    fireEvent.click(screen.getByRole('button', { name: 'Quick filter: Referral' }))
    expect(onStateChange).toHaveBeenCalledWith({ flags: ['referral'] }, { replace: true })
    fireEvent.change(screen.getByLabelText('Sort roles'), { target: { value: 'company' } })
    expect(onStateChange).toHaveBeenCalledWith({ sort: 'company' })
  })

  it('moves selection with J and K shortcuts', () => {
    const { onSelect } = setup()
    fireEvent.keyDown(window, { key: 'j' })
    expect(onSelect).toHaveBeenCalledWith('strong')
    fireEvent.keyDown(window, { key: 'k' })
    expect(onSelect).toHaveBeenCalledWith('good')
  })

  it('preserves feed scroll position when selection changes', () => {
    const { container, model, onSelect, onStateChange, rerender, state } = setup()
    const scroller = container.querySelector<HTMLElement>('[data-feed-scroll]')
    expect(scroller).not.toBeNull()
    if (!scroller) return
    scroller.scrollTop = 240

    rerender(
      <FeedView
        model={model}
        state={state}
        selectedId="strong"
        onSelect={onSelect}
        onStateChange={onStateChange}
      />,
    )

    expect(container.querySelector('[data-feed-scroll]')).toBe(scroller)
    expect(scroller.scrollTop).toBe(240)
  })

  it('keeps unselected facet choices available after filtering', () => {
    const facetData = dashboard({
      rows: [
        jobRow({ id: 'us', country: 'United States' }),
        jobRow({ id: 'india', country: 'India' }),
      ],
    })
    const state = searchSchema.parse({ country: ['United States'] })
    render(
      <FeedView
        model={buildFeed(facetData, state)}
        state={state}
        onSelect={vi.fn()}
        onStateChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'India' })).toBeInTheDocument()
  })
})
