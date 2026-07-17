import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { CompaniesView } from '@/features/companies'
import { buildCompanies } from '@/lib/companies'
import { application, dashboard, jobRow, monitoredCompany } from './factories'

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

  it('surfaces an already collected company instead of adding it again', () => {
    const onActions = vi.fn().mockResolvedValue(undefined)
    const onSelect = vi.fn()
    render(<CompaniesView
      model={buildCompanies(dashboard({
        companies: [monitoredCompany({
          id: 'google', company: 'Google', provider: '', slug: '',
          resolution_status: 'unresolved',
        })],
        rows: [jobRow({ id: 'google-role', company: 'Google' })],
        applications: [application({ job_id: 'google-role', company: 'Google' })],
      }))}
      filter="all" onFilter={vi.fn()} onSelect={onSelect}
      onOpenJob={vi.fn()} onActions={onActions}
    />)

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'google' } })

    expect(screen.getByText('Already monitored')).toBeInTheDocument()
    expect(within(screen.getByRole('button', { name: 'Open Google' }))
      .getByText('1 collected role · 1 application')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View company' })).toBeInTheDocument()
    fireEvent.submit(screen.getByLabelText('Company name').closest('form')!)
    expect(onActions).not.toHaveBeenCalled()
    expect(onSelect).toHaveBeenCalledWith('google')
  })

  it('updates a selected monitor portal without entering add mode', () => {
    const { onActions, onSelect } = setup('acme')
    fireEvent.click(screen.getByRole('button', { name: 'Edit portal' }))

    expect(screen.getByLabelText('Company name')).toHaveValue('Acme')
    expect(screen.getByLabelText('Company name')).toHaveAttribute('readonly')
    expect(screen.getByRole('button', { name: 'Save portal' })).toBeInTheDocument()
    expect(onSelect).toHaveBeenCalledWith(undefined)
    fireEvent.change(screen.getByLabelText('Careers portal URL'), {
      target: { value: 'https://acme.example/careers' },
    })
    fireEvent.submit(screen.getByLabelText('Company name').closest('form')!)
    expect(onActions).toHaveBeenCalledWith([{
      type: 'monitor.upsert', company: 'Acme', careers_url: 'https://acme.example/careers',
    }])
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