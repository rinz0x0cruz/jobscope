import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { Board } from '@/features/board'
import type { BoardColumn } from '@/lib/board'
import type { EngagementThread } from '@/lib/campaigns'
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

const engagement = (over: Partial<EngagementThread> = {}): EngagementThread => ({
  id: 'cold:one', kind: 'cold', application_job_id: '', company: 'Sentinel Labs',
  title: '', campaign_id: 'campaign:one', target_id: 'target:one',
  recipient: 'recruiter@sentinel.example', subject: 'Security research introduction',
  state: 'sent', sent_at: '2026-07-10T00:00:00Z',
  latest_activity_at: '2026-07-17T00:00:00Z', followup_count: 1,
  outbound_count: 2, reply_count: 0,
  events: [{
    direction: 'outbound', kind: 'cold', date: '2026-07-10T00:00:00Z',
    subject: 'Security research introduction', participant: 'recruiter@sentinel.example',
    summary: '', state: 'sent', signal: '', followup_number: 0,
    campaign_id: 'campaign:one', target_id: 'target:one',
  }],
  ...over,
})

describe('Board', () => {
  it('renders applications as an inbox list by default', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Applications' })).toBeInTheDocument()
    expect(screen.getByText('Acme Corp')).toBeInTheDocument()
    expect(screen.getByText('Senior Platform Engineer')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Board' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Needs attention: 1' })).toBeInTheDocument()
  })

  it('names who referred you in, on the card itself', () => {
    const columns = makeColumns()
    columns[0].cards[0].referredBy = 'Priya Nair'

    render(<Board columns={columns} onOpen={() => {}} />)

    expect(screen.getByText(/Priya Nair/)).toBeInTheDocument()
  })

  it('opens a row when clicked', () => {
    const onOpen = vi.fn()
    render(<Board columns={makeColumns()} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Acme Corp — Senior Platform Engineer' }))
    expect(onOpen).toHaveBeenCalledWith('job-1')
  })

  it('combines cold outreach with applications without treating it as a job', () => {
    const onOpenEngagement = vi.fn()
    render(<Board
      columns={makeColumns()}
      engagements={[engagement()]}
      onOpen={() => {}}
      onOpenEngagement={onOpenEngagement}
    />)

    expect(screen.getByRole('button', { name: 'All: 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Applications: 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cold outreach: 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Acme Corp — Senior Platform Engineer' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sentinel Labs — Cold outreach' }))
    expect(onOpenEngagement).toHaveBeenCalledWith('cold:one')
  })

  it('labels cold outreach without a resolved company', () => {
    const columns = makeColumns().map((column) => ({ ...column, cards: [] }))
    render(<Board
      columns={columns}
      engagements={[engagement({ company: '' })]}
      onOpen={() => {}}
    />)

    expect(screen.getByRole('button', { name: 'Unknown company — Cold outreach' })).toBeInTheDocument()
  })

  it('attaches application outreach activity to the existing application row', () => {
    render(<Board
      columns={makeColumns()}
      engagements={[engagement({
        id: 'application:job-1', kind: 'application', application_job_id: 'job-1',
        company: 'Acme Corp', title: 'Senior Platform Engineer', outbound_count: 2,
      })]}
      onOpen={() => {}}
    />)

    expect(screen.getByRole('button', { name: 'Acme Corp — Senior Platform Engineer' }))
      .toHaveTextContent('2 outreach')
  })

  it('handles a cold-only ledger with malformed dates and long text', () => {
    const columns = makeColumns().map((column) => ({ ...column, cards: [] }))
    const longCompany = 'A'.repeat(180)
    render(<Board
      columns={columns}
      engagements={[engagement({
        company: longCompany, subject: 'S'.repeat(240), sent_at: 'not-a-date',
        latest_activity_at: 'not-a-date',
      })]}
      onOpen={() => {}}
    />)

    expect(screen.getByRole('button', { name: 'All: 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Applications: 0' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Needs attention: 0' })).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: `${longCompany} — Cold outreach` })).toBeInTheDocument()
  })

  it('renders the unified empty state without crashing', () => {
    const columns = makeColumns().map((column) => ({ ...column, cards: [] }))
    render(<Board columns={columns} engagements={[]} onOpen={() => {}} />)
    expect(screen.getByText('No records in this view')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All: 0' })).toBeInTheDocument()
  })

  it('keeps delivery-unknown outreach visible as attention, not sent', () => {
    const columns = makeColumns().map((column) => ({ ...column, cards: [] }))
    render(<Board
      columns={columns}
      engagements={[engagement({
        state: 'delivery_unknown', sent_at: '',
        latest_activity_at: '2026-07-18T00:00:00Z', reply_count: 0,
      })]}
      onOpen={() => {}}
    />)

    expect(screen.getByRole('button', { name: 'Needs attention: 1' })).toBeInTheDocument()
    expect(screen.getByText('delivery unknown')).toBeInTheDocument()
    expect(screen.queryByText(/^sent$/i)).not.toBeInTheDocument()
  })

  it('switches to the Kanban columns view with headers, card pills, and empty state', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Board' }))
    expect(screen.getAllByText('Offer')).not.toHaveLength(0)
    expect(screen.getByText('Follow up')).toBeInTheDocument()
    expect(screen.getByText('HR contact')).toBeInTheDocument()
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })

  it('keeps the referrer visible after switching to the Kanban view', () => {
    const columns = makeColumns()
    columns[0].cards[0].referredBy = 'Priya Nair'
    render(<Board columns={columns} onOpen={() => {}} />)

    fireEvent.click(screen.getByRole('radio', { name: 'Board' }))

    // Switching view must not lose the referral: it is the same card either way.
    expect(screen.getByText(/Priya Nair/)).toBeInTheDocument()
  })

  it('keeps conversion analysis out of Applications', () => {
    render(<Board columns={makeColumns()} onOpen={() => {}} />)
    expect(screen.queryByRole('radio', { name: 'Conversion' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Application conversion' })).not.toBeInTheDocument()
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
    expect(screen.queryByText(/available to restore/i)).not.toBeInTheDocument()
    expect(screen.getByText('Archived applications')).toBeInTheDocument()
  })

  it('contains many recoverable applications in a compact archive list', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const recoverable = Array.from({ length: 13 }, (_, index) => ({
      ...audit.recoverable_applications[0],
      job_id: `mail:recover-${index}`,
      company: index % 2 ? 'Acme' : '',
      title: index === 0 ? 'A'.repeat(180) : 'Multiple positions',
      tombstoned_at: index === 1 ? 'not-a-date' : '2026-07-16T00:00:01Z',
    }))
    render(<Board
      columns={makeColumns()}
      onOpen={() => {}}
      audit={{ ...audit, recoverable_applications: recoverable }}
    />)

    const summary = screen.getByText('Archived applications').closest('summary')
    expect(summary).toHaveTextContent('13')
    expect(screen.queryAllByRole('button', { name: /^Restore / })).toHaveLength(0)
    fireEvent.click(summary!)
    const list = screen.getByRole('list', { name: 'Archived applications' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(13)
    const actions = within(list).getAllByRole('button', { name: /Copy recovery command/ })
    expect(new Set(actions.map((action) => action.getAttribute('aria-label'))).size).toBe(13)

    fireEvent.click(within(list).getByRole('button', {
      name: 'Copy recovery command for Multiple positions at Acme (recover-1)',
    }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      'python -m jobscope applications recover mail:recover-1 --yes',
    ))
    vi.unstubAllGlobals()
  })
})
