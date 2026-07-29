import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AnalyticsView } from '@/features/analytics'
import type { EngagementThread } from '@/lib/campaigns'
import { application } from './factories'

const outreach: EngagementThread[] = [{
  id: 'cold:one', kind: 'cold', application_job_id: '', company: 'Acme', title: '',
  campaign_id: 'campaign:one', target_id: 'target:one', recipient: 'r@acme.test',
  subject: 'Hello', state: 'replied', sent_at: '2026-07-10T00:00:00Z',
  latest_activity_at: '2026-07-12T00:00:00Z', followup_count: 0,
  outbound_count: 1, reply_count: 1,
  events: [
    { direction: 'outbound', kind: 'cold', date: '2026-07-10T00:00:00Z', subject: 'Hello', participant: 'r@acme.test', summary: '', state: 'sent', signal: '', followup_number: 0, campaign_id: 'campaign:one', target_id: 'target:one' },
    { direction: 'inbound', kind: 'reply', date: '2026-07-12T00:00:00Z', subject: 'Re: Hello', participant: 'r@acme.test', summary: '', state: 'replied', signal: 'campaign_reply', followup_number: 0, campaign_id: 'campaign:one', target_id: 'target:one' },
  ],
}]

describe('AnalyticsView', () => {
  it('renders read-only application analytics with explicit samples', () => {
    render(<AnalyticsView
      mode="applications"
      onModeChange={vi.fn()}
      applications={[
        application({ job_id: 'a', status: 'applied' }),
        application({ job_id: 'i', status: 'interview' }),
        application({ job_id: 'o', status: 'offer' }),
      ]}
      engagements={outreach}
      outreachAvailable
    />)
    expect(screen.getByRole('heading', { name: 'Analytics' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Application pipeline flow/i })).toBeInTheDocument()
    expect(screen.getByText('2 / 3')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument()
  })

  it('switches to outreach analytics and labels small samples honestly', () => {
    const onModeChange = vi.fn()
    render(<AnalyticsView
      mode="applications"
      onModeChange={onModeChange}
      applications={[]}
      engagements={outreach}
      outreachAvailable
    />)
    fireEvent.click(screen.getByRole('radio', { name: 'Outreach' }))
    expect(onModeChange).toHaveBeenCalledWith('outreach')

    render(<AnalyticsView
      mode="outreach"
      onModeChange={vi.fn()}
      applications={[]}
      engagements={outreach}
      outreachAvailable
    />)
    expect(screen.getByText('1 / 1')).toBeInTheDocument()
    expect(screen.getAllByText(/Insufficient evidence/).length).toBeGreaterThan(0)
    expect(screen.queryByText('2d')).not.toBeInTheDocument()
    expect(screen.getByText('Cold outreach')).toBeInTheDocument()
    expect(screen.getByText('Application follow-ups')).toBeInTheDocument()
    expect(screen.getByText('Requires manual Sent-folder check')).toBeInTheDocument()
    expect(screen.queryByText('Not counted as sent')).not.toBeInTheDocument()
  })

  it('ranks skill gaps against the roles they were derived from', () => {
    render(<AnalyticsView
      mode="applications"
      onModeChange={vi.fn()}
      applications={[application({ job_id: 'a', status: 'applied' })]}
      engagements={[]}
      outreachAvailable={false}
      gaps={[['kubernetes', 9], ['terraform', 4], ['yara', 1]]}
      considered={23}
    />)
    expect(screen.getByRole('heading', { name: 'Skill gaps' })).toBeInTheDocument()
    expect(screen.getByText(/Across 23 Strong\/Good\/Stretch roles/)).toBeInTheDocument()
    expect(screen.getByText('kubernetes')).toBeInTheDocument()
    expect(screen.getByText('9 roles')).toBeInTheDocument()
    expect(screen.getByText('1 role')).toBeInTheDocument()
  })

  it('says so plainly when no skill gaps remain', () => {
    render(<AnalyticsView
      mode="applications"
      onModeChange={vi.fn()}
      applications={[application({ job_id: 'a', status: 'applied' })]}
      engagements={[]}
      outreachAvailable={false}
      gaps={[]}
      considered={12}
    />)
    expect(screen.getByText(/already cover the skills these roles ask for/)).toBeInTheDocument()
  })

  it('hides the skill-gap panel entirely when nothing has been scored yet', () => {
    render(<AnalyticsView
      mode="applications"
      onModeChange={vi.fn()}
      applications={[application({ job_id: 'a', status: 'applied' })]}
      engagements={[]}
      outreachAvailable={false}
    />)
    expect(screen.queryByRole('heading', { name: 'Skill gaps' })).not.toBeInTheDocument()
  })
})