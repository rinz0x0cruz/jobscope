import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Board } from '@/features/board'
import type { BoardColumn } from '@/lib/board'

function makeColumns(): BoardColumn[] {
  return [
    {
      stage: 'applied',
      label: 'Applied',
      color: '#6b8afd',
      cards: [
        {
          id: 'job-1',
          company: 'Acme Corp',
          title: 'Senior Platform Engineer',
          stage: 'applied',
          kind: 'application',
          followup: 'due',
          outreach: true,
          daysSinceApplied: 3,
          emails: 0,
        },
      ],
    },
    {
      stage: 'offer',
      label: 'Offer',
      color: '#3fb984',
      cards: [],
    },
  ]
}

describe('Board', () => {
  it('renders applications as a table by default', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Senior Platform Engineer')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Columns' })).toBeInTheDocument()
  })

  it('opens a row when clicked', () => {
    const onOpen = vi.fn()
    render(<Board columns={makeColumns()} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Acme Corp — Senior Platform Engineer' }))
    expect(onOpen).toHaveBeenCalledWith('job-1')
  })

  it('switches to the Kanban columns view with headers, card pills, and empty state', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Columns' }))
    expect(screen.getByText('Offer')).toBeInTheDocument()
    expect(screen.getByText('Follow up')).toBeInTheDocument()
    expect(screen.getByText('HR contact')).toBeInTheDocument()
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })
})
