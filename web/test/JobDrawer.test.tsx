import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { JobDrawer, RoleReader } from '@/components/JobDrawer'
import type { EngagementThread } from '@/lib/campaigns'
import type { Application } from '@/lib/schema'
import { jobRow } from './factories'

function makeApp(): Application {
  return {
    job_id: 'mail:ibm-1',
    company: 'IBM',
    title: '',
    status: 'applied',
    applied_at: '2026-07-08T23:36:31Z',
    updated: '2026-07-10T11:00:40Z',
    source: 'gmail',
    interview_at: '',
    salary_offered: '',
    offer_accepted: '',
    timeline: [
      {
        date: '2026-07-08',
        signal: 'confirmation',
        subject: 'You have successfully submitted your IBM job application',
        from: 'ibm.com',
        summary: 'Dear applicant, thank you for applying to the Security Analyst role.',
      },
      {
        date: '2026-07-09',
        signal: 'interview',
        subject: 'Invitation to interview at IBM',
        from: 'ibm.com',
        summary: 'We would like to schedule a call to discuss the role.',
      },
      {
        date: '2026-07-17',
        signal: 'manual',
        subject: 'Assessment submitted (user-confirmed)',
        from: 'User record',
        summary: '',
      },
    ],
  }
}

function makeEngagement(over: Partial<EngagementThread> = {}): EngagementThread {
  return {
    id: 'cold:one', kind: 'cold', application_job_id: '', company: 'Sentinel Labs',
    title: '', campaign_id: 'campaign:one', target_id: 'target:one',
    recipient: 'recruiter@sentinel.example', subject: 'Security research introduction',
    state: 'replied', sent_at: '2026-07-10T00:00:00Z',
    latest_activity_at: '2026-07-11T00:00:00Z', followup_count: 0,
    outbound_count: 1, reply_count: 1,
    events: [
      { direction: 'outbound', kind: 'cold', date: '2026-07-10T00:00:00Z', subject: 'Security research introduction', participant: 'recruiter@sentinel.example', summary: '', state: 'sent', signal: '', followup_number: 0, campaign_id: 'campaign:one', target_id: 'target:one' },
      { direction: 'inbound', kind: 'reply', date: '2026-07-11T00:00:00Z', subject: 'Re: Security research introduction', participant: 'alex@sentinel.example', summary: 'Let us schedule a call.', state: 'replied', signal: 'campaign_reply', followup_number: 0, campaign_id: 'campaign:one', target_id: 'target:one' },
    ],
    ...over,
  }
}

describe('JobDrawer', () => {
  it('shows the email timeline for an applied role that has no match row', () => {
    render(
      <JobDrawer job={null} application={makeApp()} allRows={[]} onOpen={() => {}} onClose={() => {}} />,
    )
    expect(screen.getByText('Activity (3)')).toBeInTheDocument()
    expect(
      screen.getByText('You have successfully submitted your IBM job application'),
    ).toBeInTheDocument()
    expect(screen.getByText('Invitation to interview at IBM')).toBeInTheDocument()
    expect(screen.getByText(/thank you for applying/i)).toBeInTheDocument()
    expect(screen.getByText(/schedule a call/i)).toBeInTheDocument()
    expect(screen.getByText('Manual update')).toBeInTheDocument()
    expect(screen.getByText('Assessment submitted (user-confirmed)')).toBeInTheDocument()
  })

  it('renders nothing when neither a job nor an application is provided', () => {
    render(<JobDrawer job={null} application={null} allRows={[]} onOpen={() => {}} onClose={() => {}} />)
    expect(screen.queryByText(/Emails/)).not.toBeInTheDocument()
  })

  it('shows safe cold outreach correspondence and links back to Outreach', () => {
    const onOpenOutreach = vi.fn()
    render(<JobDrawer
      job={null}
      application={null}
      engagement={makeEngagement()}
      allRows={[]}
      onOpen={() => {}}
      onOpenOutreach={onOpenOutreach}
      onClose={() => {}}
    />)

    expect(screen.getByRole('heading', { name: 'Sentinel Labs' })).toBeInTheDocument()
    expect(screen.getByText('Security research introduction')).toBeInTheDocument()
    expect(screen.getByText('Let us schedule a call.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open in Outreach' }))
    expect(onOpenOutreach).toHaveBeenCalledWith('campaign:one')
    expect(document.body).not.toHaveTextContent('PRIVATE-OUTBOUND-BODY')
  })

  it('renders one inbound reply when application and outreach timelines overlap', () => {
    const app = makeApp()
    app.timeline.push({
      date: '2026-07-11', signal: 'campaign_reply',
      subject: 'Re: Security research introduction', from: 'sentinel.example',
      summary: 'Let us schedule a call.',
    })
    render(<JobDrawer
      job={null}
      application={app}
      engagement={makeEngagement()}
      allRows={[]}
      onOpen={() => {}}
      onClose={() => {}}
    />)

    expect(screen.getAllByText('Re: Security research introduction')).toHaveLength(1)
    expect(screen.getAllByText('Let us schedule a call.')).toHaveLength(1)
  })

  it('renders the same role reader outside the dialog wrapper', () => {
    render(
      <RoleReader
        job={jobRow({ title: 'Detection Engineer', company: 'Acme', rationale: 'Strong SIEM overlap' })}
        application={null}
        allRows={[]}
        onOpen={() => {}}
        onClose={() => {}}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Detection Engineer' })).toBeInTheDocument()
    expect(screen.getByText('Strong SIEM overlap')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('presents escaped descriptions and scorer rationale for reading', () => {
    render(
      <RoleReader
        job={jobRow({
          description: '**Key Responsibilities**:\n\\*Manage day\\-to\\-day operations',
          rationale: 'top: skills 100%, recency 85%, location 75% | skills matched: python, aws → research (technical role)',
        })}
        application={null}
        allRows={[]}
        onOpen={() => {}}
        onClose={() => {}}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Key Responsibilities' })).toBeInTheDocument()
    expect(screen.getByText('Manage day-to-day operations')).toBeInTheDocument()
    expect(screen.getByText('Research résumé · Technical role')).toBeInTheDocument()
    expect(screen.queryByText(/top: skills/)).not.toBeInTheDocument()
  })

  it('does not navigate to unsafe scraped links', () => {
    render(
      <RoleReader
        job={jobRow({
          id: 'unsafe-links',
          url: 'javascript:alert(1)',
          sources: [
            { source: 'primary', url: 'https://jobs.example.test/role' },
            { source: 'mirror', url: 'data:text/html,bad' },
          ],
          enrich: {
            news: [{ title: 'Untrusted news', link: 'javascript:alert(2)' }],
          },
          contacts: [{ name: 'Untrusted lead', url: 'vbscript:alert(3)' }],
        })}
        application={null}
        allRows={[]}
        onOpen={() => {}}
        onClose={() => {}}
      />,
    )

    for (const label of ['Apply on greenhouse', 'mirror', 'Untrusted news', /Untrusted lead/]) {
      expect(screen.getByText(label).closest('a')).not.toHaveAttribute('href')
    }
  })
})
