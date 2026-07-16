import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Timeline } from '@/features/timeline'
import type { Timeline as TimelineData } from '@/lib/timeline'

function makeTimeline(): TimelineData {
  return {
    agenda: [
      {
        id: 'a1',
        text: 'Follow up with Initech',
        when: '3d overdue',
        company: 'Initech',
        jobId: 'job-3',
        tone: 'stretch',
      },
    ],
    groups: [
      {
        bucket: 'week',
        label: 'This week',
        events: [
          {
            id: 'e1',
            date: '2026-06-28T00:00:00Z',
            dateLabel: '3d ago',
            signal: 'interview',
            text: 'Interview step with Acme',
            company: 'Acme',
            jobId: 'job-1',
            tone: 'good',
          },
        ],
      },
    ],
  }
}

describe('Timeline lens', () => {
  it('renders the "Up next" agenda and the grouped history timeline', () => {
    render(<Timeline timeline={makeTimeline()} onOpen={vi.fn()} />)

    expect(screen.getByText('Actions and history')).toBeInTheDocument()
    expect(screen.getByText('Action queue')).toBeInTheDocument()
    expect(screen.getByText('Event stream')).toBeInTheDocument()
    expect(screen.getByText('Follow up with Initech')).toBeInTheDocument()
    expect(screen.getByText('3d overdue')).toBeInTheDocument()
    expect(screen.getByText('This week')).toBeInTheDocument()
    expect(screen.getByText('Interview step with Acme')).toBeInTheDocument()
  })

  it('opens the job when a history event row is clicked', () => {
    const onOpen = vi.fn()
    render(<Timeline timeline={makeTimeline()} onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: /Interview step with Acme/ }))
    expect(onOpen).toHaveBeenCalledWith('job-1')
  })

  it('opens the job when an agenda row is clicked', () => {
    const onOpen = vi.fn()
    render(<Timeline timeline={makeTimeline()} onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: /Follow up with Initech/ }))
    expect(onOpen).toHaveBeenCalledWith('job-3')
  })
})
