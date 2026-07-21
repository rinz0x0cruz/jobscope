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
})