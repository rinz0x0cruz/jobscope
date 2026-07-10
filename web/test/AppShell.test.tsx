import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AppShell } from '@/app/AppShell'

const NAV_LABELS = ['Briefing', 'To apply', 'Board', 'Timeline', 'Settings']

describe('AppShell', () => {
  it('renders the five sidebar sections and marks the active one', () => {
    render(
      <AppShell active="board" onNavigate={() => {}} title="Board" search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    for (const label of NAV_LABELS) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Board' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Briefing' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the chosen section', () => {
    const onNavigate = vi.fn()
    render(
      <AppShell active="board" onNavigate={onNavigate} title="Board" search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Briefing' }))
    expect(onNavigate).toHaveBeenCalledWith('briefing')
  })

  it('renders the page title and routed children', () => {
    render(
      <AppShell active="briefing" onNavigate={() => {}} title="Briefing" search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Briefing' })).toBeInTheDocument()
    expect(screen.getByText('Routed content')).toBeInTheDocument()
  })
})
