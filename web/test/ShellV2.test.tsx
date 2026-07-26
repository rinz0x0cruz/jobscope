import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ShellV2 } from '@/app/ShellV2'
import { searchSchema } from '@/lib/urlState'
import { application, dashboard, jobRow } from './factories'

const campaignApi = vi.hoisted(() => ({ listEngagements: vi.fn() }))
const outreachApi = vi.hoisted(() => ({
  applicationUpdate: vi.fn(),
  localServeToken: vi.fn(),
}))
vi.mock('@/lib/campaigns', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/campaigns')>(),
  ...campaignApi,
}))
vi.mock('@/lib/outreach', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/outreach')>(),
  ...outreachApi,
}))

describe('ShellV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    campaignApi.listEngagements.mockResolvedValue([])
    outreachApi.localServeToken.mockResolvedValue(null)
    outreachApi.applicationUpdate.mockResolvedValue({ ok: true })
  })
  it('closes the current reader with Escape', () => {
    const job = jobRow({ id: 'selected', title: 'Security Engineer' })
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard({ rows: [job] })}
        state={searchSchema.parse({ view: 'review', job: job.id })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onStateChange).toHaveBeenCalledWith({ job: undefined }, { replace: true })
  })

  it('clears the reader when switching primary views', () => {
    const job = jobRow({ id: 'selected', title: 'Security Engineer' })
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard({ rows: [job] })}
        state={searchSchema.parse({ view: 'review', job: job.id })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: '3' })
    expect(onStateChange).toHaveBeenCalledWith({ view: 'applications', job: undefined })
  })

  it('maps shortcuts four and five to Analytics and Settings', () => {
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard()}
        state={searchSchema.parse({ view: 'review' })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )
    fireEvent.keyDown(window, { key: '4' })
    expect(onStateChange).toHaveBeenCalledWith({
      view: 'analytics', job: undefined, engagement: undefined, company: undefined, campaign: undefined,
    })
    fireEvent.keyDown(window, { key: '5' })
    expect(onStateChange).toHaveBeenCalledWith({
      view: 'settings', job: undefined, engagement: undefined, company: undefined, campaign: undefined,
    })
  })

  it('renders Analytics and stores its selected mode in URL state', () => {
    const onStateChange = vi.fn()
    const startViewTransition = vi.fn((update: () => void) => {
      update()
      return { ready: Promise.resolve() }
    })
    const original = Object.getOwnPropertyDescriptor(document, 'startViewTransition')
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: startViewTransition,
    })
    try {
      render(
        <ShellV2
          data={dashboard({ applications: [
            application({ job_id: 'a' }),
            application({ job_id: 'i', status: 'interview' }),
            application({ job_id: 'o', status: 'offer' }),
          ] })}
          state={searchSchema.parse({ view: 'analytics', tab: 'overview' })}
          onStateChange={onStateChange}
          onLock={vi.fn()}
        />,
      )

      expect(screen.getByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument()
      fireEvent.click(screen.getByRole('radio', { name: 'Outreach' }))
      expect(onStateChange).toHaveBeenCalledWith(
        { view: 'analytics', tab: 'outreach' },
        { replace: true },
      )
      expect(startViewTransition).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(document, 'startViewTransition', original)
      else Reflect.deleteProperty(document, 'startViewTransition')
    }
  })

  it('opens application Analytics from the pipeline preview', () => {
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard({ applications: [application({ job_id: 'a' })] })}
        state={searchSchema.parse({ view: 'review', tab: 'outreach' })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /Open analytics/ }))
    expect(onStateChange).toHaveBeenCalledWith({
      view: 'analytics', tab: 'overview', job: undefined, engagement: undefined,
      company: undefined, campaign: undefined,
    })
  })

  it('loads private engagement history for the Applications ledger', async () => {
    campaignApi.listEngagements.mockResolvedValue([{
      id: 'cold:one', kind: 'cold', application_job_id: '', company: 'Sentinel Labs',
      title: '', campaign_id: 'campaign:one', target_id: 'target:one',
      recipient: 'recruiter@sentinel.example', subject: 'Security introduction',
      state: 'sent', sent_at: '2026-07-10T00:00:00Z', latest_activity_at: '2026-07-10T00:00:00Z',
      followup_count: 0, outbound_count: 1, reply_count: 0, events: [],
    }])
    render(
      <ShellV2
        data={dashboard()}
        serveToken="private-token"
        state={searchSchema.parse({ view: 'applications' })}
        onStateChange={vi.fn()}
        onLock={vi.fn()}
      />,
    )

    expect(await screen.findByRole('button', { name: 'Sentinel Labs — Cold outreach' })).toBeInTheDocument()
    expect(campaignApi.listEngagements).toHaveBeenCalledWith('private-token')
  })

  it('closes an engagement drawer with Escape', () => {
    const onStateChange = vi.fn()
    render(
      <ShellV2
        data={dashboard()}
        state={searchSchema.parse({ view: 'applications', engagement: 'cold:one' })}
        onStateChange={onStateChange}
        onLock={vi.fn()}
      />,
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onStateChange).toHaveBeenCalledWith({
      job: undefined, engagement: undefined,
    }, { replace: true })
  })

  it('filters engagement history with the shared search query', async () => {
    campaignApi.listEngagements.mockResolvedValue([
      {
        id: 'cold:sentinel', kind: 'cold', application_job_id: '', company: 'Sentinel Labs',
        title: '', campaign_id: 'campaign:one', target_id: 'target:one',
        recipient: 'recruiter@sentinel.example', subject: 'Security introduction',
        state: 'sent', sent_at: '2026-07-10T00:00:00Z', latest_activity_at: '2026-07-10T00:00:00Z',
        followup_count: 0, outbound_count: 1, reply_count: 0, events: [],
      },
      {
        id: 'cold:orbit', kind: 'cold', application_job_id: '', company: 'Orbit Systems',
        title: '', campaign_id: 'campaign:two', target_id: 'target:two',
        recipient: 'recruiter@orbit.example', subject: 'Detection introduction',
        state: 'sent', sent_at: '2026-07-10T00:00:00Z', latest_activity_at: '2026-07-10T00:00:00Z',
        followup_count: 0, outbound_count: 1, reply_count: 0, events: [],
      },
    ])
    render(
      <ShellV2
        data={dashboard()}
        serveToken="private-token"
        state={searchSchema.parse({ view: 'applications', q: 'sentinel' })}
        onStateChange={vi.fn()}
        onLock={vi.fn()}
      />,
    )

    expect(await screen.findByRole('button', { name: 'Sentinel Labs — Cold outreach' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Orbit Systems — Cold outreach' })).not.toBeInTheDocument()
  })

  it('keeps applications usable when engagement loading fails', async () => {
    campaignApi.listEngagements.mockRejectedValue(new Error('private API unavailable'))
    const job = jobRow({ id: 'job-1', title: 'Security Engineer', company: 'Acme' })
    render(
      <ShellV2
        data={dashboard({ rows: [job], applications: [application({ job_id: job.id })] })}
        serveToken="private-token"
        state={searchSchema.parse({ view: 'applications' })}
        onStateChange={vi.fn()}
        onLock={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Acme — Engineer' })).toBeInTheDocument()
    await waitFor(() => expect(campaignApi.listEngagements).toHaveBeenCalledWith('private-token'))
  })

  it('does not request private engagement data without a serve token', () => {
    render(
      <ShellV2
        data={dashboard()}
        state={searchSchema.parse({ view: 'applications' })}
        onStateChange={vi.fn()}
        onLock={vi.fn()}
      />,
    )
    expect(campaignApi.listEngagements).not.toHaveBeenCalled()
  })

  it('shows read-only Outreach from the encrypted snapshot without a serve token', () => {
    render(
      <ShellV2
        data={dashboard({
          outreach_snapshot: {
            read_only: true,
            campaigns: [{
              id: 'campaign:one', name: 'India security outreach', purpose: 'cold',
              status: 'draft', sector: 'cybersecurity', region: 'India', requested_count: 1,
              weights: { region: 0.5, compensation: 0.3, growth: 0.2 }, criteria: {},
              resume_name: 'research', daily_limit: 2, min_spacing_hours: 4,
              timezone: 'Asia/Kolkata', send_window_start: '10:00', send_window_end: '17:00',
              created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z',
              counts: { draft: 1 }, target_count: 1, delivered_count: 0, response_count: 0,
            }],
            details: [], engagements: [],
          },
        })}
        state={searchSchema.parse({ view: 'campaigns' })}
        onStateChange={vi.fn()}
        onLock={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Outreach' })).toBeInTheDocument()
    expect(screen.getByText('Read-only encrypted snapshot')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'India security outreach' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create batch' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete draft' })).not.toBeInTheDocument()
    expect(screen.getByText('Pages is view-only')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open private workspace/ })).toHaveAttribute(
      'href',
      'http://127.0.0.1:8799/#/?view=campaigns&campaign=campaign%3Aone',
    )
    expect(campaignApi.listEngagements).not.toHaveBeenCalled()
  })

  it('updates application state after saving offer details', async () => {
    outreachApi.localServeToken.mockResolvedValue('private-token')
    outreachApi.applicationUpdate.mockResolvedValue({
      ok: true,
      updated: {
        job_id: 'application:one', interview_at: '',
        salary_offered: 'INR 28 LPA', offer_accepted: '',
      },
    })
    render(
      <ShellV2
        data={dashboard({ applications: [application({ job_id: 'application:one' })] })}
        serveToken="private-token"
        state={searchSchema.parse({ view: 'applications', job: 'application:one' })}
        onStateChange={vi.fn()}
        onLock={vi.fn()}
      />,
    )

    const salary = await screen.findByLabelText('Offer comp')
    fireEvent.change(salary, { target: { value: 'INR 28 LPA' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(outreachApi.applicationUpdate).toHaveBeenCalledWith(
      'application:one', 'private-token', {
        interview_at: '', salary_offered: 'INR 28 LPA', offer_accepted: '',
      },
    ))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled())
  })
})
