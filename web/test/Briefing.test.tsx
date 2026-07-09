import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Briefing } from '@/features/briefing'
import type { Briefing as BriefingData } from '@/lib/briefing'

function makeBriefing(): BriefingData {
  return {
    headline: 'You have 1 offer on the table. 1 thing needs you.',
    subhead: '12 roles tracked · “Warming up”',
    figures: [{ key: 'offers', label: 'Offer', value: 1 }],
    moved: [],
    needs: [
      {
        id: 'n1',
        text: 'Nudge Initech — 10d since applying',
        company: 'Initech',
        jobId: 'job-9',
        tone: 'stretch',
      },
    ],
    matches: [{ jobId: 'm1', company: 'Stripe', title: 'Backend Engineer', tier: 'Strong', score: 92 }],
  }
}

describe('Briefing lens', () => {
  it('renders the headline, the figure, and the empty "This week" line', () => {
    render(<Briefing briefing={makeBriefing()} onOpen={vi.fn()} />)

    expect(
      screen.getByText('You have 1 offer on the table. 1 thing needs you.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Offer')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('Quiet week so far.')).toBeInTheDocument()
  })

  it('opens the job when a needs row is clicked', () => {
    const onOpen = vi.fn()
    render(<Briefing briefing={makeBriefing()} onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: /Nudge Initech/ }))
    expect(onOpen).toHaveBeenCalledWith('job-9')
  })

  it('renders a fresh match and opens it on click', () => {
    const onOpen = vi.fn()
    render(<Briefing briefing={makeBriefing()} onOpen={onOpen} />)

    expect(screen.getByText('Stripe')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Stripe/ }))
    expect(onOpen).toHaveBeenCalledWith('m1')
  })
})
