import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Application } from '@/lib/schema'
import { ApplicationsSection } from '@/components/applications/views'

const app = (p: Partial<Application>): Application => ({
  job_id: p.job_id ?? 'j' + Math.random().toString(36).slice(2),
  company: p.company ?? 'Acme',
  title: p.title ?? 'Engineer',
  status: p.status ?? 'applied',
  applied_at: p.applied_at ?? '2026-07-01',
  updated: p.updated ?? '2026-07-02',
  source: p.source ?? 'inbox',
  timeline: p.timeline ?? [],
})

const apps: Application[] = [
  app({ company: 'Alpha', status: 'applied' }),
  app({ company: 'Beta', status: 'interview' }),
  app({ company: 'Gamma', status: 'rejected' }),
]

beforeEach(() => localStorage.clear())

// Feature: List / Compact / Table / Grouped view switcher on the Applications tab.
describe('ApplicationsSection view switcher', () => {
  it('defaults to List with one card per application', () => {
    render(<ApplicationsSection apps={apps} />)
    expect(screen.getByTitle('List')).toHaveAttribute('aria-pressed', 'true')
    expect(document.querySelectorAll('article')).toHaveLength(3)
  })

  it('switches to Table (header + a row per app) and persists the choice', async () => {
    render(<ApplicationsSection apps={apps} />)
    await userEvent.click(screen.getByTitle('Table'))
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(1 + 3)
    expect(localStorage.getItem('jobscope-apps-view')).toBe('table')
  })

  it('sorts the table ascending by a clicked column header', async () => {
    render(<ApplicationsSection apps={apps} />)
    await userEvent.click(screen.getByTitle('Table'))
    await userEvent.click(screen.getByText(/^Company/))
    const firstDataRow = within(screen.getByRole('table')).getAllByRole('row')[1]
    expect(firstDataRow).toHaveTextContent('Alpha')
  })

  it('splits into collapsible status groups in the Grouped view', async () => {
    render(<ApplicationsSection apps={apps} />)
    await userEvent.click(screen.getByTitle('Grouped'))
    // one expandable header per present status (applied / interview / rejected)
    expect(screen.getAllByRole('button', { expanded: true })).toHaveLength(3)
    expect(document.querySelectorAll('article')).toHaveLength(3)
  })
})
