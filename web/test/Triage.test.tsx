import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Triage } from '@/features/triage'
import type { TriageQueue } from '@/lib/triage'

function makeQueue(): TriageQueue {
  return {
    items: [
      {
        jobId: 'j1',
        company: 'Acme',
        title: 'Platform Engineer',
        tier: 'Strong',
        score: 90,
        location: 'San Francisco',
        remote: true,
        ageDays: 2,
        brief: 'Strong platform fit — matches your infra background.',
        url: 'https://x',
      },
      {
        jobId: 'j2',
        company: 'Globex',
        title: 'Backend Engineer',
        tier: 'Good',
        score: 78,
        location: 'Berlin',
        remote: false,
        ageDays: 0,
        brief: 'Solid backend match.',
        url: 'https://y',
      },
    ],
    total: 2,
  }
}

describe('Triage lens', () => {
  it('renders the first item and the remaining count', () => {
    render(<Triage queue={makeQueue()} onOpen={vi.fn()} />)
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('2 left')).toBeInTheDocument()
  })

  it('opens the current job when Details is clicked', () => {
    const onOpen = vi.fn()
    render(<Triage queue={makeQueue()} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: /Details/ }))
    expect(onOpen).toHaveBeenCalledWith('j1')
  })

  it('advances to the next item when Skip is clicked', () => {
    render(<Triage queue={makeQueue()} onOpen={vi.fn()} />)
    expect(screen.getByText('Acme')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Skip/ }))

    expect(screen.getByText('Globex')).toBeInTheDocument()
    expect(screen.getByText('1 left')).toBeInTheDocument()
  })

  it('shows the "All caught up" empty state when everything is skipped', () => {
    render(<Triage queue={makeQueue()} onOpen={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Skip/ }))
    fireEvent.click(screen.getByRole('button', { name: /Skip/ }))
    expect(screen.getByText('All caught up')).toBeInTheDocument()
  })
})
