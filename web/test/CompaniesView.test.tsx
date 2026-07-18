import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

function renderCompany(item: ReturnType<typeof monitoredCompany>, onActions = vi.fn().mockResolvedValue(undefined)) {
  render(<CompaniesView
    model={buildCompanies(dashboard({ companies: [item] }))}
    filter="all"
    selectedId={item.id}
    onFilter={vi.fn()}
    onSelect={vi.fn()}
    onOpenJob={vi.fn()}
    onActions={onActions}
  />)
  return onActions
}

describe('CompaniesView', () => {
  it('resolves an unresolved monitor once and blocks duplicate clicks', async () => {
    let finish: (() => void) | undefined
    const onActions = vi.fn(() => new Promise<void>((resolve) => { finish = resolve }))
    const unresolved = monitoredCompany({
      id: 'company:ntt', company: 'NTT DATA', lifecycle: 'watching', status: 'active',
      resolution_status: 'unresolved', provider: '', slug: '', careers_url: '',
    })
    renderCompany(unresolved, onActions)

    const resolveButton = screen.getByRole('button', { name: 'Resolve & scan' })
    fireEvent.click(resolveButton)
    fireEvent.click(resolveButton)
    expect(onActions).toHaveBeenCalledTimes(1)
    expect(onActions).toHaveBeenCalledWith([
      { type: 'monitor.scan', monitor_id: unresolved.id },
    ])
    expect(resolveButton).toBeDisabled()
    finish?.()
    await waitFor(() => expect(resolveButton).toBeEnabled())
  })

  it('resumes a paused monitor before allowing a scan', async () => {
    const onActions = vi.fn(async () => undefined)
    const paused = monitoredCompany({
      id: 'company:paused', company: 'Acme', lifecycle: 'watching', status: 'paused',
      resolution_status: 'resolved', provider: 'greenhouse', slug: 'acme',
    })
    renderCompany(paused, onActions)

    expect(screen.queryByRole('button', { name: 'Scan jobs' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resume to scan' }))
    await waitFor(() => expect(onActions).toHaveBeenCalledWith([
      { type: 'monitor.status', monitor_id: paused.id, status: 'active' },
    ]))
  })

  it('keeps authoritative posting counts when hidden reviews are not rendered', () => {
    const item = monitoredCompany({
      id: 'company:ntt', company: 'NTT DATA', pending_count: 4,
      resolution_status: 'resolved', provider: 'phenom', slug: 'NTT1GLOBAL',
    })
    const visible = jobRow({ id: 'visible', company: 'NTT DATA', tier: 'Stretch' })
    const hiddenReview = {
      job_id: 'hidden-skip', state: 'pending' as const, origins: ['monitored' as const],
      monitor_ids: [item.id], first_seen: '', reviewed_at: '',
    }
    const model = buildCompanies(dashboard({
      companies: [item], rows: [visible], reviews: [hiddenReview],
    }))

    expect(model.allItems[0].pending_count).toBe(4)
    expect(model.allItems[0].pendingJobs).toEqual([])
  })

  it('shows the latest scan funnel and exclusion reasons', () => {
    const item = monitoredCompany({
      id: 'company:ntt', company: 'NTT DATA', provider: 'phenom', slug: 'NTT1GLOBAL',
    })
    render(<CompaniesView
      model={buildCompanies(dashboard({ companies: [item] }))}
      filter="all" selectedId={item.id} onFilter={vi.fn()} onSelect={vi.fn()}
      onOpenJob={vi.fn()} onActions={vi.fn().mockResolvedValue(undefined)}
      scanFunnels={{
        [item.id]: {
          board: 76, geo_eligible: 11, title_eligible: 11,
          details_attempted: 11, details_hydrated: 11,
          details_failed: 0, details_truncated: 0,
          experience_eligible: 4, matched: 4,
          skip_reasons: { geography: 65, experience_cap: 7 },
        },
      }}
    />)

    const funnel = screen.getByRole('region', { name: 'Latest scan funnel' })
    expect(funnel).toHaveTextContent('Board76')
    expect(funnel).toHaveTextContent('Geo11')
    expect(funnel).toHaveTextContent('Experience4')
    expect(funnel).toHaveTextContent('Matched4')
    expect(funnel).toHaveTextContent('Full details hydrated 11/11')
    expect(funnel).toHaveTextContent('Geography 65 · Experience cap 7')
  })
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

  it('shows the preferred recruiter and keeps jobs/contact scans separate', async () => {
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
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find recruiter' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Find recruiter' }))
    await waitFor(() => expect(onActions).toHaveBeenCalledWith([
      { type: 'monitor.contacts', monitor_id: 'acme' },
    ]))
  })
})
