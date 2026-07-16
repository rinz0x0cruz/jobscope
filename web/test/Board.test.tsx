import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Board } from '@/features/board'
import type { BoardColumn } from '@/lib/board'
import type { ActivityAudit } from '@/lib/schema'

function makeColumns(): BoardColumn[] {
  return [
    {
      stage: 'applied',
      label: 'Applied',
      color: '#6b8afd',
      cards: [
        {
          id: 'job-1',
          company: 'Acme Corp',
          title: 'Senior Platform Engineer',
          stage: 'applied',
          kind: 'application',
          followup: 'due',
          outreach: true,
          daysSinceApplied: 3,
          emails: 0,
        },
      ],
    },
    {
      stage: 'offer',
      label: 'Offer',
      color: '#3fb984',
      cards: [],
    },
  ]
}

const audit: ActivityAudit = {
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
  decisions: [],
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

describe('Board', () => {
  it('renders applications as an inbox list by default', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.getByText('Application inbox')).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Senior Platform Engineer')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Board' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Needs attention: 1' })).toBeInTheDocument()
  })

  it('opens a row when clicked', () => {
    const onOpen = vi.fn()
    render(<Board columns={makeColumns()} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Acme Corp — Senior Platform Engineer' }))
    expect(onOpen).toHaveBeenCalledWith('job-1')
  })

  it('switches to the Kanban columns view with headers, card pills, and empty state', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Board' }))
    expect(screen.getAllByText('Offer')).not.toHaveLength(0)
    expect(screen.getByText('Follow up')).toBeInTheDocument()
    expect(screen.getByText('HR contact')).toBeInTheDocument()
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })

  it('filters the inbox to applications needing attention', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Needs attention: 1' }))
    expect(screen.getByLabelText('1 shown')).toBeInTheDocument()
    expect(screen.getByText('Senior Platform Engineer')).toBeInTheDocument()
  })

  it('shows the latest reconciliation delta', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} audit={audit} />)
    expect(screen.getByLabelText('Last reconciliation')).toHaveTextContent('121 → 99')
    expect(screen.getByLabelText('Last reconciliation')).toHaveTextContent('1 recoverable')
  })
})
