import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { CompaniesView } from '@/features/companies'
import { buildCompanies } from '@/lib/companies'
import { application, dashboard, jobRow, monitoredCompany } from './factories'

function setup(selectedId?: string) {
  const onActions = vi.fn().mockResolvedValue(undefined)
  const onSelect = vi.fn()
  render(<CompaniesView
    model={buildCompanies(dashboard({ companies: [monitoredCompany({
      id: 'acme', company: 'Acme', careers_url: 'https://acme.example/jobs',
    })] }))}
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
    expect(screen.getByText('Companies and career portals')).toBeInTheDocument()
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
          resolution_status: 'unresolved', lifecycle: 'known', status: 'removed',
        })],
        rows: [jobRow({ id: 'google-role', company: 'Google' })],
        applications: [application({ job_id: 'google-role', company: 'Google' })],
      }))}
      filter="all" onFilter={vi.fn()} onSelect={onSelect}
      onOpenJob={vi.fn()} onActions={onActions}
    />)

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'google' } })

    expect(screen.getByText('Already known')).toBeInTheDocument()
    expect(within(screen.getByRole('button', { name: 'Open Google' }))
      .getByText('1 collected role · 1 application')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View company' })).toBeInTheDocument()
    fireEvent.submit(screen.getByLabelText('Company name').closest('form')!)
    expect(onActions).not.toHaveBeenCalled()
    expect(onSelect).toHaveBeenCalledWith('google')
  })

  it('promotes a known application company into the watchlist', () => {
    const onActions = vi.fn().mockResolvedValue(undefined)
    const onOpenJob = vi.fn()
    const company = monitoredCompany({
      id: 'google', company: 'Google', lifecycle: 'known', status: 'removed',
      provider: '', slug: '', resolution_status: 'unresolved',
      added_from: ['application'],
    })
    render(<CompaniesView
      model={buildCompanies(dashboard({
        companies: [company],
        applications: [application({ job_id: 'google-role', company: 'Google' })],
        rows: [jobRow({ id: 'google-role', company: 'Google', title: 'Security Engineer' })],
      }))}
      filter="known" selectedId="google" onFilter={vi.fn()} onSelect={vi.fn()}
      onOpenJob={onOpenJob} onActions={onActions}
    />)

    expect(within(screen.getByRole('heading', { name: 'Google' }).closest('header')!)
      .getByText('Known from application')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Scan jobs' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Security Engineer/ }))
    expect(onOpenJob).toHaveBeenCalledWith('google-role')
    fireEvent.click(screen.getByRole('button', { name: 'Monitor company' }))
    expect(onActions).toHaveBeenCalledWith([{
      type: 'monitor.upsert', company: 'Google', careers_url: '',
    }])
  })

  it('opens a partial existing match from its result card', () => {
    const { onActions, onSelect } = setup()
    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'ac' } })

    fireEvent.click(screen.getByRole('button', { name: 'Open Acme' }))

    expect(onSelect).toHaveBeenCalledWith('acme')
    expect(onActions).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Company name')).toHaveValue('')
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

  it('exits portal edit mode when browsing to a company', () => {
    const { onSelect } = setup('acme')
    fireEvent.click(screen.getByRole('button', { name: 'Edit portal' }))
    expect(screen.getByRole('button', { name: 'Save portal' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Acme/ }))

    expect(onSelect).toHaveBeenLastCalledWith('acme')
    expect(screen.getByLabelText('Company name')).toHaveValue('')
    expect(screen.getByLabelText('Careers portal URL')).toHaveValue('')
    expect(screen.getByLabelText('Company name')).not.toHaveAttribute('readonly')
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