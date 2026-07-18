import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AppShell } from '@/app/AppShell'

const NAV_LABELS = ['Review', 'Companies', 'Pipeline', 'Applications', 'Activity', 'Settings']

describe('AppShell', () => {
  it('omits snapshot locking when no lock handler is available', () => {
    render(
      <AppShell active="review" onNavigate={() => {}} search="" onSearch={() => {}}>
        <div>Content</div>
      </AppShell>,
    )
    expect(screen.queryByRole('button', { name: 'Lock' })).not.toBeInTheDocument()
  })

  it('renders the six primary sections and marks the active one', () => {
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
    expect(nav.getByRole('button', { name: 'Review' })).not.toHaveAttribute('aria-current')
  })

  it('fires onNavigate with the chosen section', () => {
    const onNavigate = vi.fn()
    render(
      <AppShell active="applications" onNavigate={onNavigate} search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    const nav = within(screen.getByRole('navigation', { name: 'Primary' }))
    fireEvent.click(nav.getByRole('button', { name: 'Review' }))
    expect(onNavigate).toHaveBeenCalledWith('review')
  })

  it('renders the page title and routed children', () => {
    render(
      <AppShell active="review" onNavigate={() => {}} search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Review' })).toBeInTheDocument()
    expect(screen.getByText('Routed content')).toBeInTheDocument()
  })

  it('keeps Activity and Settings reachable from mobile More', () => {
    const onNavigate = vi.fn()
    render(
      <AppShell active="activity" onNavigate={onNavigate} search="" onSearch={() => {}}>
        <div>Routed content</div>
      </AppShell>,
    )
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Mobile primary' })).getByRole('button', { name: 'More' }))
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(onNavigate).toHaveBeenCalledWith('settings')
  })

  it('surfaces queued monitoring changes as a sync command', () => {
    const onSyncChanges = vi.fn()
    render(
      <AppShell active="review" onNavigate={() => {}} search="" onSearch={() => {}} pendingChanges={3} onSyncChanges={onSyncChanges}>
        <div>Routed content</div>
      </AppShell>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Sync 3 queued changes' }))
    expect(onSyncChanges).toHaveBeenCalledOnce()
  })

  it('exposes a labeled Gmail scan command', () => {
    const onRefresh = vi.fn()
    render(
      <AppShell active="review" onNavigate={() => {}} search="" onSearch={() => {}} onRefresh={onRefresh}>
        <div>Routed content</div>
      </AppShell>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Scan Gmail' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })
})
