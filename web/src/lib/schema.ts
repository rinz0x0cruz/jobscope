// Typed mirror of the Python data contract emitted by
// `jobscope dashboard --emit-json` (render.py: build_data / _job_record /
// _overview_data / _application_records). Keep this 1:1 with the Python shapes.

export type Tier = 'Strong' | 'Good' | 'Stretch' | 'Skip'

export interface StockSummary {
  ticker?: string
  price?: number
  change_pct?: number
  market_cap?: string
  public?: boolean
  currency?: string
  week52_low?: number
  week52_high?: number
  week52_pos_pct?: number
}

export interface CompSummary {
  levels_fyi?: string
  levels_search?: string
  min?: number
  max?: number
  interval?: string
  currency?: string
  source?: string
  source_url?: string
  range?: string
}

export interface RedditSummary {
  sentiment?: string | null
  summary?: string | null
  count?: number
}

export interface NewsItem {
  title?: string
  link?: string
  published?: string
  source?: string
}

export interface EnrichSummary {
  stock?: StockSummary
  comp?: CompSummary
  reddit?: RedditSummary
  news?: NewsItem[]
  glassdoor?: Record<string, unknown>
}

export interface Contact {
  name?: string | null
  title?: string | null
  url?: string | null
}

export interface JobSource {
  source: string
  url: string
}

export interface JobRow {
  id: string
  title: string
  company: string
  location: string
  remote: boolean
  remote_scope: string
  url: string
  source: string
  score: number
  tier: Tier
  base: string
  salary: string
  salary_min: number | null
  salary_max: number | null
  salary_interval: string
  currency: string
  size: string
  funding: string
  country: string
  place: string
  industry: string | null
  rationale: string
  blocked: boolean
  posted: string | null
  first_seen: string
  status: string
  last_seen: string
  closed_at: string
  posted_age_days: number | null
  stale: boolean
  remote_mismatch: boolean
  sources: JobSource[]
  coverage_pct: number | null
  enrich: EnrichSummary
  brief: string
  description: string
  contacts: Contact[]
  recruiter: CompanyContact | null
}

export interface Overview {
  funnel: Record<string, number>
  gaps: [string, number][]
  considered: number
  targets: string[]
}

// Encrypted whole-site blob (scripts/build-secure-apps.mjs): AES-256-GCM over the
// full un-redacted dashboard payload, decrypted in-browser with the passphrase.
// Present only in a published (`publish.ps1 -Encrypted`) build.
export interface EncBlob {
  v: number
  kdf: string
  iter: number
  salt: string
  iv: string
  ct: string
}

// Published builds ship the heavy ciphertext as a separate file and bake only a
// tiny pointer, so the initial bundle stays lean (the blob is fetched on unlock).
// The baked marker is either this pointer or an inline EncBlob.
export interface EncPointer {
  v: number
  url: string
}

export type EncRef = EncBlob | EncPointer

// One row of an application's email timeline (render.py: _application_records,
// the `timeline[]` items). Every key is always emitted (Python defaults to '').
// `summary` is a deterministic one-line preview of the email body, present only
// when inbox.store_snippets is enabled (else '').
export interface ApplicationEvent {
  date: string
  signal: string
  subject: string
  from: string
  summary: string
}

// A tracked application for the Applications board (render.py: _application_records).
// Emitted only for the private build; the public payload sends `applications: []`.
export interface Application {
  job_id: string
  company: string
  title: string
  status: string
  applied_at: string
  updated: string
  source: string
  interview_at: string
  salary_offered: string
  offer_accepted: string
  timeline: ApplicationEvent[]
}

// Résumé-derived search profile (render._profile_data). Present behind the site
// unlock; null in the public build.
export interface Profile {
  resume: string
  seniority: string
  years_experience: number
  search_terms: string[]
  locations: string[]
  remote: boolean
  top_skills: string[]
  name: string
  available: string[]
}

// A discovered HR/recruiting contact for an applied company.
export interface CompanyContact {
  email: string
  confidence: string // high | medium | low
  source: string // recruiter | discovered | hunter | apollo | role_inbox
  note: string
}

// Pre-computed HR contacts for a company you're actively applied to. Emitted only
// for the private build; the public payload sends `applied_outreach: []`.
export interface AppliedCompany {
  company: string
  domain: string
  status: string
  applied_at: string
  contacts: CompanyContact[]
}

export type MonitorStatus = 'active' | 'paused' | 'removed'
export type MonitorResolution = 'resolved' | 'unresolved' | 'unsupported'
export type ReviewState = 'pending' | 'saved' | 'dismissed'
export type ReviewOrigin = 'monitored' | 'discovery' | 'legacy'

export interface MonitoredCompany {
  id: string
  company: string
  provider: string
  slug: string
  careers_url: string
  status: MonitorStatus
  resolution_status: MonitorResolution
  added_from: string[]
  checked_at: string
  last_success_at: string
  health_status: string
  health_detail: string
  board_count: number
  open_matches: number
  pending_count: number
  saved_count: number
  contact_domain: string
  contacts_checked_at: string
  recruiter_count: number
  recruiter: CompanyContact | null
}

export interface JobReview {
  job_id: string
  state: ReviewState
  origins: ReviewOrigin[]
  monitor_ids: string[]
  first_seen: string
  reviewed_at: string
}

export type ReconciliationAction = 'recompute' | 'reclassify' | 'restore'
export type ReconciliationRunStatus = 'running' | 'completed' | 'failed'

export interface ReconciliationRun {
  id: string
  action: ReconciliationAction
  initiator: 'cli' | 'local_refresh' | 'cloud_refresh' | 'user'
  started_at: string
  completed_at: string
  status: ReconciliationRunStatus
  applications_before: number
  applications_after: number | null
  events_before: number
  events_after: number | null
  groups_count: number
  instances_count: number
  reclassified_count: number
  dropped_count: number
  tombstoned_count: number
  restored_count: number
  error_code: string
  schema_version: number
  baseline_only: boolean
}

export interface ReconciliationDecision {
  id: string
  run_id: string
  sequence: number
  base_job_id: string
  application_id: string
  decision_type: string
  old_status: string
  new_status: string
  old_signal: string
  new_signal: string
  reason_code: string
  recoverable: boolean
  created_at: string
}

export interface RecoverableApplication {
  job_id: string
  status: string
  company: string
  title: string
  source: string
  tombstoned_at: string
  tombstone_reason: string
  reconciliation_run_id: string
  reconciliation_exempt: number
}

export interface ActivityAudit {
  recent_runs: ReconciliationRun[]
  selected_run_id: string
  decisions: ReconciliationDecision[]
  recoverable_applications: RecoverableApplication[]
}

export interface DashboardData {
  generated: string
  total: number
  rows: JobRow[]
  overview: Overview
  applications?: Application[]
  profile: Profile | null
  applied_outreach: AppliedCompany[]
  companies: MonitoredCompany[]
  reviews: JobReview[]
  activity_audit: ActivityAudit
}

export function normalizeDashboardData(data: DashboardData): DashboardData {
  const legacy = data as DashboardData & {
    companies?: MonitoredCompany[]
    reviews?: JobReview[]
    activity_audit?: Partial<ActivityAudit>
  }
  return {
    ...data,
    rows: data.rows.map((row) => {
      const legacyRow = row as JobRow & Partial<Pick<JobRow,
        'salary_min' | 'salary_max' | 'salary_interval' | 'currency' | 'recruiter'>>
      return {
        ...row,
        salary_min: legacyRow.salary_min ?? null,
        salary_max: legacyRow.salary_max ?? null,
        salary_interval: legacyRow.salary_interval ?? '',
        currency: legacyRow.currency ?? '',
        recruiter: legacyRow.recruiter ?? null,
      }
    }),
    applications: data.applications ?? [],
    activity_audit: {
      recent_runs: legacy.activity_audit?.recent_runs ?? [],
      selected_run_id: legacy.activity_audit?.selected_run_id ?? '',
      decisions: legacy.activity_audit?.decisions ?? [],
      recoverable_applications: legacy.activity_audit?.recoverable_applications ?? [],
    },
    companies: (legacy.companies ?? []).map((company) => {
      const legacyCompany = company as MonitoredCompany & Partial<Pick<MonitoredCompany,
        'contact_domain' | 'contacts_checked_at' | 'recruiter_count' | 'recruiter'>>
      return {
        ...company,
        contact_domain: legacyCompany.contact_domain ?? '',
        contacts_checked_at: legacyCompany.contacts_checked_at ?? '',
        recruiter_count: legacyCompany.recruiter_count ?? 0,
        recruiter: legacyCompany.recruiter ?? null,
      }
    }),
    reviews: legacy.reviews?.length ? legacy.reviews : data.rows.map((row) => ({
      job_id: row.id,
      state: 'saved' as const,
      origins: ['legacy' as const],
      monitor_ids: [],
      first_seen: row.first_seen || data.generated || '',
      reviewed_at: row.first_seen || data.generated || '',
    })),
  }
}

export const TIERS: Tier[] = ['Strong', 'Good', 'Stretch', 'Skip']

export const TIER_COLOR: Record<Tier, string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}
