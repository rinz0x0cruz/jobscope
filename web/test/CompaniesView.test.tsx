import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CompaniesView } from '@/features/companies'
import { buildCompanies } from '@/lib/companies'
import { dashboard, monitoredCompany } from './factories'

function setup(selectedId?: string) {
  const onActions = vi.fn().mockResolvedValue(undefined)
  const onSelect = vi.fn()
  const onResolve = vi.fn().mockResolvedValue({
    ok: true, company: 'Beta', status: 'resolved', provider: 'lever', slug: 'beta',
    careers_url: 'https://jobs.lever.co/beta', detail: '', count: 8, matched: 2, results: [],
  })
  render(<CompaniesView
    model={buildCompanies(dashboard({ companies: [monitoredCompany({ id: 'acme', company: 'Acme' })] }))}
    filter="all"
    selectedId={selectedId}
    onFilter={vi.fn()}
    onSelect={onSelect}
    onOpenJob={vi.fn()}
    onActions={onActions}
    onResolve={onResolve}
  />)
  return { onActions, onResolve, onSelect }
}

describe('CompaniesView', () => {
  it('renders monitored companies and status filters', () => {
    setup()
    expect(screen.getByText('Monitored career portals')).toBeInTheDocument()
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Needs setup' })).toBeInTheDocument()
  })

  it('resolves and confirms a new company', async () => {
    const { onActions, onResolve } = setup()
    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'Beta' } })
    fireEvent.submit(screen.getByLabelText('Company name').closest('form')!)
    expect(onResolve).toHaveBeenCalledWith('Beta', '')
    expect(await screen.findByText(/8 openings/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Monitor company' }))
    expect(onActions).toHaveBeenCalledWith([expect.objectContaining({ type: 'monitor.upsert', company: 'Beta' })])
  })

  it('loads the selected monitor into the portal editor', () => {
    const { onSelect } = setup('acme')
    fireEvent.click(screen.getByRole('button', { name: 'Edit portal' }))

    expect(screen.getByLabelText('Company name')).toHaveValue('Acme')
    expect(onSelect).toHaveBeenCalledWith(undefined)
  })

  it('shows the preferred recruiter and scans jobs plus recruiter contacts', () => {
    const onActions = vi.fn().mockResolvedValue(undefined)
    const company = monitoredCompany({
      id: 'acme', company: 'Acme', recruiter_count: 3,
      contacts_checked_at: '2026-07-17T10:00:00Z',
      recruiter: {
        email: 'cyber@acme.com', confidence: 'medium', source: 'apollo',
        note: 'Cybersecurity Recruiter via Apollo',
      },
    })
    render(<CompaniesView
      model={buildCompanies(dashboard({ companies: [company] }))}
      filter="all" selectedId="acme" onFilter={vi.fn()} onSelect={vi.fn()}
      onOpenJob={vi.fn()} onActions={onActions} onResolve={vi.fn()}
    />)

    expect(screen.getByRole('link', { name: 'cyber@acme.com' }))
      .toHaveAttribute('href', 'mailto:cyber@acme.com')
    expect(screen.getByText(/Cybersecurity Recruiter via Apollo/)).toBeInTheDocument()
    expect(screen.getByText('3 candidates')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Scan jobs + recruiter' }))
    expect(onActions).toHaveBeenCalledWith([{ type: 'monitor.scan', monitor_id: 'acme' }])
  })
})