import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CompaniesView } from '@/features/companies'
import { buildCompanies } from '@/lib/companies'
import { dashboard, monitoredCompany } from './factories'

function setup(selectedId?: string) {
  const onActions = vi.fn().mockResolvedValue(undefined)
  const onSelect = vi.fn()
  render(<CompaniesView
    model={buildCompanies(dashboard({ companies: [monitoredCompany({ id: 'acme', company: 'Acme' })] }))}
    filter="all"
    selectedId={selectedId}
    onFilter={vi.fn()}
    onSelect={onSelect}
    onOpenJob={vi.fn()}
    onActions={onActions}
  />)
  return { onActions, onSelect }
}

describe('CompaniesView', () => {
  it('renders monitored companies and status filters', () => {
    setup()
    expect(screen.getByText('Monitored career portals')).toBeInTheDocument()
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Needs setup' })).toBeInTheDocument()
  })

  it('adds a company immediately without resolving its portal', async () => {
    const { onActions } = setup()
    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'Beta' } })
    fireEvent.submit(screen.getByLabelText('Company name').closest('form')!)
    expect(onActions).toHaveBeenCalledWith([
      { type: 'monitor.upsert', company: 'Beta', careers_url: '' },
    ])
  })

  it('loads the selected monitor into the portal editor', () => {
    const { onSelect } = setup('acme')
    fireEvent.click(screen.getByRole('button', { name: 'Edit portal' }))

    expect(screen.getByLabelText('Company name')).toHaveValue('Acme')
    expect(onSelect).toHaveBeenCalledWith(undefined)
  })

  it('shows the preferred recruiter and keeps jobs/contact scans separate', () => {
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
      onOpenJob={vi.fn()} onActions={onActions}
    />)

    expect(screen.getByRole('link', { name: 'cyber@acme.com' }))
      .toHaveAttribute('href', 'mailto:cyber@acme.com')
    expect(screen.getByText(/Cybersecurity Recruiter via Apollo/)).toBeInTheDocument()
    expect(screen.getByText('3 candidates')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Scan jobs' }))
    expect(onActions).toHaveBeenCalledWith([{ type: 'monitor.scan', monitor_id: 'acme' }])
    fireEvent.click(screen.getByRole('button', { name: 'Find recruiter' }))
    expect(onActions).toHaveBeenCalledWith([{ type: 'monitor.contacts', monitor_id: 'acme' }])
  })
})