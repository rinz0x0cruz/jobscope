import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AppShell } from '@/app/AppShell'

const NAV_LABELS = ['Feed', 'Pipeline', 'Applications', 'Activity', 'Settings']

describe('AppShell', () => {
  it('renders the five sidebar sections and marks the active one', () => {
    render(
      <AppShell active="applications" onNavigate={() => {}} search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    const nav = within(screen.getByRole('navigation', { name: 'Primary' }))
    for (const label of NAV_LABELS) {
      expect(nav.getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(nav.getByRole('button', { name: 'Applications' })).toHaveAttribute('aria-current', 'page')
    expect(nav.getByRole('button', { name: 'Feed' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the chosen section', () => {
    const onNavigate = vi.fn()
    render(
      <AppShell active="applications" onNavigate={onNavigate} search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    const nav = within(screen.getByRole('navigation', { name: 'Primary' }))
    fireEvent.click(nav.getByRole('button', { name: 'Feed' }))
    expect(onNavigate).toHaveBeenCalledWith('feed')
  })

  it('renders the page title and routed children', () => {
    render(
      <AppShell active="feed" onNavigate={() => {}} search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Feed' })).toBeInTheDocument()
    expect(screen.getByText('Routed content')).toBeInTheDocument()
  })
})
