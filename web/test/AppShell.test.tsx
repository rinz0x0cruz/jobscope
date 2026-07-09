import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AppShell } from '@/app/AppShell'

const NAV_LABELS = ['Overview', 'Jobs', 'Applications', 'Outreach', 'Settings']

describe('AppShell', () => {
  it('renders the five sidebar sections and marks the active one', () => {
    render(
      <AppShell active="jobs" onNavigate={() => {}} title="Jobs" search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    for (const label of NAV_LABELS) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Jobs' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Overview' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the chosen section', () => {
    const onNavigate = vi.fn()
    render(
      <AppShell active="jobs" onNavigate={onNavigate} title="Jobs" search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(onNavigate).toHaveBeenCalledWith('overview')
  })

  it('renders the page title and routed children', () => {
    render(
      <AppShell active="overview" onNavigate={() => {}} title="Overview" search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByText('Routed content')).toBeInTheDocument()
  })
})
