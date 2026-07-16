import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { JobDrawer, RoleReader } from '@/components/JobDrawer'
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
    ],
  }
}

describe('JobDrawer', () => {
  it('shows the email timeline for an applied role that has no match row', () => {
    render(
      <JobDrawer job={null} application={makeApp()} allRows={[]} onOpen={() => {}} onClose={() => {}} />,
    )
    expect(screen.getByText('Emails (2)')).toBeInTheDocument()
    expect(
      screen.getByText('You have successfully submitted your IBM job application'),
    ).toBeInTheDocument()
    expect(screen.getByText('Invitation to interview at IBM')).toBeInTheDocument()
    expect(screen.getByText(/thank you for applying/i)).toBeInTheDocument()
    expect(screen.getByText(/schedule a call/i)).toBeInTheDocument()
  })

  it('renders nothing when neither a job nor an application is provided', () => {
    render(<JobDrawer job={null} application={null} allRows={[]} onOpen={() => {}} onClose={() => {}} />)
    expect(screen.queryByText(/Emails/)).not.toBeInTheDocument()
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
})
