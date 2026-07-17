export type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'cancelled'
export type CampaignTargetState =
  | 'ranked'
  | 'needs_contact'
  | 'draft'
  | 'approved'
  | 'sent'
  | 'skipped'
  | 'failed'
  | 'replied'
  | 'opted_out'

export interface CampaignContact {
  email: string
  source: string
  confidence: string
  note: string
}

export interface CampaignEvidence {
  region?: string[]
  compensation?: string[]
  growth?: string[]
  compensation_basis?: string
}

export interface Campaign {
  id: string
  name: string
  status: CampaignStatus
  sector: string
  region: string
  requested_count: number
  weights: { region: number; compensation: number; growth: number }
  criteria: Record<string, unknown>
  resume_name: string
  daily_limit: number
  min_spacing_hours: number
  timezone: string
  send_window_start: string
  send_window_end: string
  created_at: string
  updated_at: string
}

export interface CampaignSummary extends Campaign {
  counts: Partial<Record<CampaignTargetState, number>>
  target_count: number
  delivered_count: number
  response_count: number
}

export interface CampaignHistoryItem {
  target_id: string
  campaign_id: string
  company: string
  recipient: string
  subject: string
  state: CampaignTargetState
  outbound_message_id: string
  sent_at: string
  replied_at: string
  reply_event_id: string
  reply_from?: string
  reply_subject?: string
  reply_signal?: string
  reply_date?: string
}

export interface CampaignTarget {
  id: string
  campaign_id: string
  company_key: string
  company: string
  state: CampaignTargetState
  rank_score: number
  region_score: number
  compensation_score: number
  growth_score: number
  evidence_coverage: number
  evidence: CampaignEvidence
  domain: string
  contacts: CampaignContact[]
  selected_email: string
  selected_source: string
  selected_confidence: string
  selected_note: string
  subject: string
  body: string
  resume_path: string
  resume_sha256: string
  approval_hash: string
  approved_at: string
  scheduled_at: string
  outbound_message_id: string
  sent_at: string
  replied_at: string
  reply_event_id: string
  error_code: string
  error_detail: string
  created_at: string
  updated_at: string
}

export interface CampaignDetailResult {
  ok: boolean
  error?: string
  campaign: Campaign
  targets: CampaignTarget[]
  counts: Partial<Record<CampaignTargetState, number>>
  history: CampaignHistoryItem[]
  reply_tracking: { last_checked_at: string; last_status: string }
  ranking?: {
    eligible_count: number
    follow_up: Array<{ company: string; job_id: string; status: string }>
    blocked: Array<{ company: string; reason: string }>
  }
}

export interface CampaignActionResult {
  ok: boolean
  error?: string
  code?: string
  sent?: boolean
  target?: CampaignTarget
  campaign?: Campaign
  targets?: CampaignTarget[]
  counts?: Partial<Record<CampaignTargetState, number>>
  processed?: number
  drafted?: number
  needs_contact?: number
  failed?: number
  remaining?: number
  checked_at?: string
  inbox_status?: string
  pending?: number
  replied?: number
  opted_out?: number
}

const endpoint = (path: string) => `${location.origin}/${path}`

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), {
    ...init,
    cache: 'no-store',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      'X-Refresh-Token': token,
      ...init?.headers,
    },
  })
  const result = await response.json() as { error?: string }
  if (!response.ok) throw new Error(result.error || `Campaign request failed (${response.status})`)
  return result as T
}

export async function listCampaigns(token: string): Promise<CampaignSummary[]> {
  const result = await request<{ ok: boolean; campaigns: CampaignSummary[] }>('api/campaigns', token)
  return result.campaigns
}

export function getCampaign(token: string, campaignId: string): Promise<CampaignDetailResult> {
  return request<CampaignDetailResult>(
    `api/campaigns/detail?id=${encodeURIComponent(campaignId)}`,
    token,
  )
}

export function createCampaign(
  token: string,
  payload: {
    name: string
    requested_count: number
    weights: { region: number; compensation: number; growth: number }
    resume_name?: string
  },
): Promise<CampaignDetailResult> {
  return request<CampaignDetailResult>('api/campaigns', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function campaignAction(
  token: string,
  payload: Record<string, unknown> & { action: string },
): Promise<CampaignActionResult> {
  return request<CampaignActionResult>('api/campaigns/action', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}