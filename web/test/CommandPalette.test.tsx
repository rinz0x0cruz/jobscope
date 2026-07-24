import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CommandPalette } from '@/features/command'
import { jobRow } from './factories'

const rows = [
  jobRow({ id: 'a', company: 'Stripe', title: 'Security Engineer' }),
  jobRow({ id: 'b', company: 'Datadog', title: 'Detection Engineer' }),
]

function setup(over: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    rows,
    onNavigate: vi.fn(),
    onOpenJob: vi.fn(),
    onRefresh: vi.fn(),
    onToggleTheme: vi.fn(),
    onLock: vi.fn(),
    ...over,
  }
  render(<CommandPalette {...props} />)
  return props
}

describe('CommandPalette', () => {
  it('lists lenses, actions, and recent roles when open', () => {
    setup()
    expect(screen.getByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Companies')).toBeInTheDocument()
    expect(screen.getByText('Toggle theme')).toBeInTheDocument()
    expect(screen.getByText('Stripe')).toBeInTheDocument()
  })

  it('navigates to a lens and closes', () => {
    const p = setup()
    fireEvent.click(screen.getByText('Applications'))
    expect(p.onNavigate).toHaveBeenCalledWith('applications')
    expect(p.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('opens a job on select', () => {
    const p = setup()
    fireEvent.click(screen.getByText('Datadog'))
    expect(p.onOpenJob).toHaveBeenCalledWith('b')
  })

  it('fuzzy-filters jobs by the typed query', () => {
    setup()
    fireEvent.change(screen.getByPlaceholderText('Search jobs or jump to…'), {
      target: { value: 'stripe' },
    })
    expect(screen.getByText('Stripe')).toBeInTheDocument()
    expect(screen.queryByText('Datadog')).not.toBeInTheDocument()
  })

  it('jumps to a typed destination with Enter', () => {
    const p = setup()
    const input = screen.getByPlaceholderText('Search jobs or jump to…')
    fireEvent.change(input, { target: { value: 'Analytics' } })

    expect(screen.queryByText('Review')).not.toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(p.onNavigate).toHaveBeenCalledWith('analytics')
    expect(p.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('opens a fuzzy-matched job with Enter', () => {
    const p = setup()
    const input = screen.getByPlaceholderText('Search jobs or jump to…')
    fireEvent.change(input, { target: { value: 'Stripe' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(p.onOpenJob).toHaveBeenCalledWith('a')
    expect(p.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('runs the refresh action', () => {
    const p = setup()
    fireEvent.click(screen.getByText('Refresh · scan mail'))
    expect(p.onRefresh).toHaveBeenCalled()
  })
})
