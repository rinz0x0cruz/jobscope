import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { FeedView } from '@/features/feed'
import { buildFeed } from '@/lib/feed'
import { searchSchema } from '@/lib/urlState'
import { dashboard, jobRow, review } from './factories'

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
  reviews: [review({ job_id: 'strong' }), review({ job_id: 'good' })],
})

function setup(over: Record<string, unknown> = {}) {
  const state = searchSchema.parse(over)
  const model = buildFeed(data, state)
  const onSelect = vi.fn()
  const onStateChange = vi.fn()
  const onReviewState = vi.fn()
  const onMonitorCompany = vi.fn()
  const view = render(
    <FeedView
      model={model}
      state={state}
      onSelect={onSelect}
      onStateChange={onStateChange}
      onReviewState={onReviewState}
      onMonitorCompany={onMonitorCompany}
    />,
  )
  return { ...view, model, onSelect, onStateChange, onReviewState, onMonitorCompany, state }
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

  it('shows compensation, public sentiment, news, and recruiter intelligence', () => {
    const intelData = dashboard({
      rows: [jobRow({
        id: 'intel', title: 'Product Security Engineer',
        salary_min: 110_000, salary_max: 130_000, salary_interval: 'year', currency: 'USD',
        enrich: {
          comp: { min: 90_000, max: 110_000, interval: 'year', currency: 'USD' },
          glassdoor: { rating: 4.2 },
          reddit: { sentiment: 'positive', count: 8 },
          news: [{ title: 'One' }, { title: 'Two' }],
        },
        recruiter: {
          email: 'recruiter@acme.example', confidence: 'high', source: 'recruiter', note: '',
        },
      })],
      reviews: [review({ job_id: 'intel' })],
    })
    const state = searchSchema.parse({})
    render(
      <FeedView
        model={buildFeed(intelData, state)} state={state}
        onSelect={vi.fn()} onStateChange={vi.fn()}
        onReviewState={vi.fn()} onMonitorCompany={vi.fn()}
      />,
    )

    expect(screen.getByText('120% market')).toBeInTheDocument()
    expect(screen.getByText('Glassdoor 4.2')).toBeInTheDocument()
    expect(screen.getByText('Reddit positive')).toBeInTheDocument()
    expect(screen.getByText('2 news')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Email recruiter for Product Security Engineer' }))
      .toHaveAttribute('href', 'mailto:recruiter@acme.example')
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

  it('saves and dismisses pending review rows', () => {
    const { onReviewState } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Save Security Engineer' }))
    expect(onReviewState).toHaveBeenCalledWith('strong', 'saved')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Security Engineer' }))
    expect(onReviewState).toHaveBeenCalledWith('strong', 'dismissed')
  })

  it('moves selection with J and K shortcuts', () => {
    const { onSelect } = setup()
    fireEvent.keyDown(window, { key: 'j' })
    expect(onSelect).toHaveBeenCalledWith('strong')
    fireEvent.keyDown(window, { key: 'k' })
    expect(onSelect).toHaveBeenCalledWith('good')
  })

  it('preserves feed scroll position when selection changes', () => {
    const { container, model, onSelect, onStateChange, onReviewState, onMonitorCompany, rerender, state } = setup()
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
        onReviewState={onReviewState}
        onMonitorCompany={onMonitorCompany}
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
      reviews: [review({ job_id: 'us' }), review({ job_id: 'india' })],
    })
    const state = searchSchema.parse({ country: ['United States'] })
    render(
      <FeedView
        model={buildFeed(facetData, state)}
        state={state}
        onSelect={vi.fn()}
        onStateChange={vi.fn()}
        onReviewState={vi.fn()}
        onMonitorCompany={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'India' })).toBeInTheDocument()
  })

  it('offers company monitoring for discovery results', () => {
    const discoveryData = dashboard({
      rows: [jobRow({ id: 'discovery', company: 'Beta', title: 'Cloud Security Engineer', url: 'https://jobs.lever.co/beta/1' })],
      reviews: [review({ job_id: 'discovery', origins: ['discovery'] })],
    })
    const state = searchSchema.parse({ reviewBucket: 'discovery' })
    const onMonitorCompany = vi.fn()
    render(
      <FeedView
        model={buildFeed(discoveryData, state)}
        state={state}
        onSelect={vi.fn()}
        onStateChange={vi.fn()}
        onReviewState={vi.fn()}
        onMonitorCompany={onMonitorCompany}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Monitor Beta' }))
    expect(onMonitorCompany).toHaveBeenCalledWith('discovery', 'Beta', 'https://jobs.lever.co/beta/1')
  })
})
