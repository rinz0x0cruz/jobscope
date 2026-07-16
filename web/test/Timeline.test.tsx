import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Timeline } from '@/features/timeline'
import type { ActivityAudit } from '@/lib/schema'
import type { Timeline as TimelineData } from '@/lib/timeline'

function makeTimeline(): TimelineData {
  return {
    agenda: [
      {
        id: 'a1',
        text: 'Follow up with Initech',
        when: '3d overdue',
        company: 'Initech',
        jobId: 'job-3',
        tone: 'stretch',
      },
    ],
    groups: [
      {
        bucket: 'week',
        label: 'This week',
        events: [
          {
            id: 'e1',
            date: '2026-06-28T00:00:00Z',
            dateLabel: '3d ago',
            signal: 'interview',
            text: 'Interview step with Acme',
            company: 'Acme',
            jobId: 'job-1',
            tone: 'good',
          },
        ],
      },
    ],
  }
}

function makeAudit(): ActivityAudit {
  return {
    recent_runs: [{
      id: 'reconcile:one',
      action: 'recompute',
      initiator: 'cli',
      started_at: '2026-07-16T00:00:00Z',
      completed_at: '2026-07-16T00:00:01Z',
      status: 'completed',
      applications_before: 121,
      applications_after: 99,
      events_before: 140,
      events_after: 138,
      groups_count: 98,
      instances_count: 99,
      reclassified_count: 1,
      dropped_count: 2,
      tombstoned_count: 1,
      restored_count: 0,
      error_code: '',
      schema_version: 1,
      baseline_only: false,
    }],
    selected_run_id: 'reconcile:one',
    decisions: [{
      id: 'reconcile:one:000001',
      run_id: 'reconcile:one',
      sequence: 1,
      base_job_id: 'mail:recover',
      application_id: 'mail:recover',
      decision_type: 'application_tombstoned',
      old_status: 'rejected',
      new_status: '',
      old_signal: '',
      new_signal: '',
      reason_code: 'orphan_mail_application',
      recoverable: true,
      created_at: '2026-07-16T00:00:01Z',
    }],
    recoverable_applications: [{
      job_id: 'mail:recover',
      status: 'rejected',
      company: 'Acme',
      title: 'Security Engineer',
      source: 'inbox',
      tombstoned_at: '2026-07-16T00:00:01Z',
      tombstone_reason: 'orphan_mail_application',
      reconciliation_run_id: 'reconcile:one',
      reconciliation_exempt: 0,
    }],
  }
}

describe('Timeline lens', () => {
  it('renders the "Up next" agenda and the grouped history timeline', () => {
    render(<Timeline timeline={makeTimeline()} onOpen={vi.fn()} />)

    expect(screen.getByText('Actions and history')).toBeInTheDocument()
    expect(screen.getByText('Action queue')).toBeInTheDocument()
    expect(screen.getByText('Event stream')).toBeInTheDocument()
    expect(screen.getByText('Follow up with Initech')).toBeInTheDocument()
    expect(screen.getByText('3d overdue')).toBeInTheDocument()
    expect(screen.getByText('This week')).toBeInTheDocument()
    expect(screen.getByText('Interview step with Acme')).toBeInTheDocument()
  })

  it('opens the job when a history event row is clicked', () => {
    const onOpen = vi.fn()
    render(<Timeline timeline={makeTimeline()} onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: /Interview step with Acme/ }))
    expect(onOpen).toHaveBeenCalledWith('job-1')
  })

  it('opens the job when an agenda row is clicked', () => {
    const onOpen = vi.fn()
    render(<Timeline timeline={makeTimeline()} onOpen={onOpen} />)

    fireEvent.click(screen.getByRole('button', { name: /Follow up with Initech/ }))
    expect(onOpen).toHaveBeenCalledWith('job-3')
  })

  it('shows controlled reconciliation details and confirms recovery', () => {
    const onRecover = vi.fn()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(
      <Timeline
        timeline={makeTimeline()}
        onOpen={vi.fn()}
        audit={makeAudit()}
        onRecover={onRecover}
      />,
    )

    expect(screen.getByText(/121 → 99 applications/)).toBeInTheDocument()
    expect(screen.getByText('Groups')).toBeInTheDocument()
    expect(screen.getByText('98')).toBeInTheDocument()
    expect(screen.getByText('Instances')).toBeInTheDocument()
    expect(screen.getByText('99')).toBeInTheDocument()
    expect(screen.getByText('Reclassified')).toBeInTheDocument()
    expect(screen.getByText('Tombstoned')).toBeInTheDocument()
    expect(screen.getByText('Application tombstoned')).toBeInTheDocument()
    expect(screen.getByText('Orphan mail application')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('reconciliation-exempt'))
    expect(onRecover).toHaveBeenCalledWith('mail:recover')
    confirm.mockRestore()
  })
})
