import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CampaignsView } from '@/features/campaigns'
import type { Campaign, CampaignDetailResult, CampaignSummary, CampaignTarget } from '@/lib/campaigns'

const api = vi.hoisted(() => ({
  campaignAction: vi.fn(),
  createCampaign: vi.fn(),
  getCampaign: vi.fn(),
  listCampaigns: vi.fn(),
}))

vi.mock('@/lib/campaigns', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/campaigns')>(),
  ...api,
}))

const campaign: Campaign = {
  id: 'campaign:1', name: 'India security', status: 'draft', sector: 'cybersecurity',
  region: 'India', requested_count: 1,
  weights: { region: 0.5, compensation: 0.3, growth: 0.2 }, criteria: {},
  resume_name: '', daily_limit: 2, min_spacing_hours: 4, timezone: 'Asia/Kolkata',
  send_window_start: '10:00', send_window_end: '17:00',
  created_at: '2026-07-17T00:00:00Z', updated_at: '2026-07-17T00:00:00Z',
}

const target: CampaignTarget = {
  id: 'target:1', campaign_id: campaign.id, company_key: 'acme', company: 'Acme',
  state: 'draft', rank_score: 86.3, region_score: 1, compensation_score: 0.75,
  growth_score: 0.73, evidence_coverage: 0.92,
  evidence: { region: ['Bengaluru role'], compensation: ['INR salary'], growth: ['Hiring'] },
  domain: 'acme.example', contacts: [{
    email: 'recruiter@acme.example', source: 'hunter', confidence: 'medium',
    note: 'Security recruiter via Hunter.io',
  }],
  selected_email: 'recruiter@acme.example', selected_source: 'hunter',
  selected_confidence: 'medium', selected_note: 'Security recruiter via Hunter.io',
  subject: 'Security opportunities', body: 'Hello from Jane.', resume_path: 'resume.pdf',
  resume_sha256: 'resume-hash',
  approval_hash: '', approved_at: '', scheduled_at: '', sent_at: '', replied_at: '',
  outbound_message_id: '',
  reply_event_id: '',
  error_code: '', error_detail: '', created_at: campaign.created_at, updated_at: campaign.updated_at,
}

const detail: CampaignDetailResult = {
  ok: true, campaign, targets: [target], counts: { draft: 1 },
  reply_tracking: { last_checked_at: '2026-07-17T06:05:00Z', last_status: 'ok' },
  history: [{
    target_id: 'sent:1', campaign_id: campaign.id, company: 'Sentinel Co',
    recipient: 'recruiter@sentinel.example', subject: 'Security role', state: 'replied',
    outbound_message_id: 'jobscope-campaign-1@example.com',
    sent_at: '2026-07-17T05:30:00Z', replied_at: '2026-07-17T06:00:00Z',
    reply_event_id: 'reply:1', reply_from: 'alex@sentinel.example',
    reply_subject: 'Re: Security role', reply_signal: 'campaign_reply',
    reply_date: '2026-07-17T06:00:00Z',
  }],
}

const summary: CampaignSummary = {
  ...campaign, counts: { draft: 1 }, target_count: 1,
  delivered_count: 0, response_count: 0,
}

describe('CampaignsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('approves only the exact saved draft and has no bulk approval', async () => {
    api.listCampaigns.mockResolvedValue([summary])
    api.getCampaign.mockResolvedValue(detail)
    api.campaignAction
      .mockResolvedValueOnce({ ok: true, target })
      .mockResolvedValueOnce({ ok: true, target: { ...target, state: 'approved' } })
    const onSelect = vi.fn()

    render(<CampaignsView
      token="csrf"
      selectedId={campaign.id}
      onSelect={onSelect}
      onOpenApplications={vi.fn()}
    />)

    expect(screen.getByRole('heading', { name: 'Outreach' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Cold batches' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Follow-ups' })).not.toBeChecked()
    expect(await screen.findByRole('heading', { name: 'India security' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve all/i })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Sent email and reply history' })).toHaveTextContent('Sentinel Co')
    expect(screen.getByRole('region', { name: 'Sent email and reply history' })).toHaveTextContent('Re: Security role')
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Edited exact draft.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(api.campaignAction).toHaveBeenCalledTimes(2))
    expect(api.campaignAction).toHaveBeenNthCalledWith(1, 'csrf', {
      action: 'draft', target_id: target.id, selected_email: target.selected_email,
      subject: target.subject, body: 'Edited exact draft.',
    })
    expect(api.campaignAction).toHaveBeenNthCalledWith(2, 'csrf', {
      action: 'approve', target_id: target.id,
    })
  })

  it('approves and sends one target without activating the campaign', async () => {
    api.listCampaigns.mockResolvedValue([summary])
    api.getCampaign.mockResolvedValue(detail)
    api.campaignAction.mockResolvedValue({ ok: true, target })

    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    fireEvent.click(await screen.findByRole('button', { name: 'Approve and send now' }))

    await waitFor(() => expect(api.campaignAction).toHaveBeenCalledTimes(3))
    expect(api.campaignAction.mock.calls.map(([, payload]) => payload.action)).toEqual([
      'draft', 'approve', 'send_now',
    ])
  })

  it('keeps bulk recruiter discovery available for needs-contact targets', async () => {
    const unresolved = {
      ...target, state: 'needs_contact' as const, selected_email: '',
      subject: '', body: '', contacts: [],
    }
    const unresolvedDetail = {
      ...detail, targets: [unresolved], counts: { needs_contact: 1 }, history: [],
    }
    api.listCampaigns.mockResolvedValue([{
      ...summary, counts: { needs_contact: 1 },
    }])
    api.getCampaign.mockResolvedValue(unresolvedDetail)
    api.campaignAction.mockResolvedValue({
      ok: true, processed: 1, drafted: 0, needs_contact: 1, failed: 0, remaining: 0,
    })

    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    fireEvent.click(await screen.findByRole('button', { name: 'Find recruiters' }))
    await waitFor(() => expect(api.campaignAction).toHaveBeenCalledWith('csrf', {
      action: 'discover_pending', campaign_id: campaign.id, limit: 5, fetch: true,
    }))
  })

  it('keeps bulk recruiter discovery available after a provider failure', async () => {
    const failed = {
      ...target, state: 'failed' as const, selected_email: '', subject: '', body: '',
      contacts: [], error_code: 'contact_discovery_failed',
      error_detail: 'temporary provider failure',
    }
    api.listCampaigns.mockResolvedValue([{ ...summary, counts: { failed: 1 } }])
    api.getCampaign.mockResolvedValue({
      ...detail, targets: [failed], counts: { failed: 1 }, history: [],
    })

    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    expect(await screen.findByRole('button', { name: 'Find recruiters' })).toBeInTheDocument()
  })

  it('checks inbox replies from the campaign workspace', async () => {
    api.listCampaigns.mockResolvedValue([summary])
    api.getCampaign.mockResolvedValue(detail)
    api.campaignAction.mockResolvedValue({
      ok: true, replied: 1, opted_out: 0, inbox_status: 'ok',
    })

    render(<CampaignsView
      token="csrf"
      selectedId={campaign.id}
      onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    fireEvent.click(await screen.findByRole('button', { name: 'Check replies' }))

    await waitFor(() => expect(api.campaignAction).toHaveBeenCalledWith('csrf', {
      action: 'check_replies', fetch: true,
    }))
  })

  it('requires explicit resolution for an unknown delivery and hides send actions', async () => {
    const unknown = {
      ...target,
      state: 'approved' as const,
      error_code: 'delivery_unknown',
      error_detail: 'SMTP outcome unknown',
      outbound_message_id: 'jobscope-campaign-1@example.com',
    }
    api.listCampaigns.mockResolvedValue([summary])
    api.getCampaign.mockResolvedValue({
      ...detail, targets: [unknown], counts: { approved: 1 }, history: [],
    })
    api.campaignAction.mockResolvedValue({
      ok: true, target: { ...unknown, state: 'draft', error_code: '' },
    })
    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    expect(await screen.findByText('SMTP outcome unknown')).toBeInTheDocument()
    expect(screen.getAllByText('delivery unknown')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Confirmed in Sent' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send now' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve and send now' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmed not sent' }))

    await waitFor(() => expect(api.campaignAction).toHaveBeenCalledWith('csrf', {
      action: 'resolve_delivery', target_id: target.id, outcome: 'not_sent',
    }))
  })

  it('confirms and permanently deletes a draft campaign', async () => {
    api.listCampaigns.mockResolvedValueOnce([summary]).mockResolvedValueOnce([])
    api.getCampaign.mockResolvedValue({ ...detail, history: [] })
    api.campaignAction.mockResolvedValue({
      ok: true, deleted_campaign_id: campaign.id, deleted_campaign_name: campaign.name,
    })
    const onSelect = vi.fn()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<CampaignsView
      token="csrf"
      selectedId={campaign.id}
      onSelect={onSelect}
      onOpenApplications={vi.fn()}
    />)

    fireEvent.click(await screen.findByRole('button', { name: 'Delete draft' }))

    await waitFor(() => expect(api.campaignAction).toHaveBeenCalledWith('csrf', {
      action: 'delete', campaign_id: campaign.id,
    }))
    expect(confirm).toHaveBeenCalledWith(
      'Permanently delete the draft campaign “India security”?',
    )
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(undefined))
    confirm.mockRestore()
  })

  it('builds a follow-up queue without approving or sending', async () => {
    const followupDetail = {
      ...detail,
      campaign: { ...campaign, id: 'campaign:followup', purpose: 'followup' as const },
    }
    api.listCampaigns.mockResolvedValueOnce([summary]).mockResolvedValueOnce([{
      ...summary, ...followupDetail.campaign,
    }])
    api.getCampaign.mockResolvedValue(detail)
    api.createCampaign.mockResolvedValue(followupDetail)
    const onSelect = vi.fn()
    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={onSelect}
      onOpenApplications={vi.fn()}
    />)

    fireEvent.click(screen.getByRole('radio', { name: 'Follow-ups' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Build follow-up queue' }))

    await waitFor(() => expect(api.createCampaign).toHaveBeenCalledWith('csrf', {
      name: 'Recruiter follow-ups', requested_count: 10,
      purpose: 'followup', include_cold: true, include_applications: true,
    }))
    expect(api.campaignAction).not.toHaveBeenCalled()
    expect(onSelect).toHaveBeenCalledWith('campaign:followup')
  })

  it('shows follow-up source and original-recipient provenance in the queue', async () => {
    const followupCampaign = {
      ...campaign, id: 'campaign:followup', name: 'Recruiter follow-ups',
      purpose: 'followup' as const,
    }
    const followupTarget = {
      ...target, campaign_id: followupCampaign.id, rank_score: 12,
      source_target_id: 'target:cold', recipient_locked: true,
      evidence: { followup_source: 'cold' as const, anchor: '2026-07-05T00:00:00Z' },
    }
    const followupDetail = {
      ...detail, campaign: followupCampaign, targets: [followupTarget], history: [],
    }
    api.listCampaigns.mockResolvedValue([{
      ...summary, ...followupCampaign,
    }])
    api.getCampaign.mockResolvedValue(followupDetail)

    render(<CampaignsView
      token="csrf" selectedId={followupCampaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    expect(await screen.findByRole('heading', { name: 'Recruiter follow-ups' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Age' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Source' })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'India / comp / growth' })).not.toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Prior cold email' })).toBeInTheDocument()
    expect(screen.getByText('Original locked')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Recipient' })).toBeDisabled()
  })

  it('keeps multiword target states on one line', async () => {
    api.listCampaigns.mockResolvedValue([summary])
    api.getCampaign.mockResolvedValue({
      ...detail,
      targets: [{ ...target, state: 'needs_contact', selected_email: '' }],
      counts: { needs_contact: 1 },
      history: [],
    })

    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    expect(await screen.findAllByText('needs contact')).toHaveLength(2)
    for (const badge of screen.getAllByText('needs contact')) {
      expect(badge).toHaveClass('whitespace-nowrap')
    }
  })

  it('survives rapid cold and follow-up composer switches', async () => {
    api.listCampaigns.mockResolvedValue([summary])
    api.getCampaign.mockResolvedValue(detail)
    render(<CampaignsView
      token="csrf" selectedId={campaign.id} onSelect={vi.fn()}
      onOpenApplications={vi.fn()}
    />)

    await screen.findByRole('heading', { name: 'India security' })
    fireEvent.click(screen.getByRole('radio', { name: 'Follow-ups' }))
    expect(screen.getByRole('button', { name: 'Build follow-up queue' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Cold batches' }))
    expect(screen.getByRole('button', { name: 'Create batch' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Build follow-up queue' })).not.toBeInTheDocument()
  })
})