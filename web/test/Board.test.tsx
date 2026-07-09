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
  it('renders every column label', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.getByText('Applied')).toBeInTheDocument()
    expect(screen.getByText('Offer')).toBeInTheDocument()
  })

  it('renders a card with its company, title, and status pills', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Senior Platform Engineer')).toBeInTheDocument()
    expect(screen.getByText('Follow up')).toBeInTheDocument()
    expect(screen.getByText('HR contact')).toBeInTheDocument()
  })

  it('calls onOpen with the card id when the card is clicked', () => {
    const onOpen = vi.fn()
    render(<Board columns={makeColumns()} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Acme Corp — Senior Platform Engineer' }))
    expect(onOpen).toHaveBeenCalledWith('job-1')
  })

  it('shows an empty-state placeholder for a column with no cards', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })
})
