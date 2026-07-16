// Shared factories for web unit tests. Not a test file itself (no `.test`), so
// vitest won't try to run it.

import type { Application, DashboardData, JobReview, JobRow, MonitoredCompany } from '@/lib/schema'

export function jobRow(over: Partial<JobRow> & Pick<JobRow, 'id'>): JobRow {
  return {
    id: over.id,
    title: 'Engineer',
    company: 'Acme',
    location: 'Remote',
    remote: true,
    remote_scope: '',
    url: '',
    source: 'greenhouse',
    score: 70,
    tier: 'Good',
    base: '',
    salary: '',
    salary_min: null,
    salary_max: null,
    salary_interval: '',
    currency: '',
    size: '',
    funding: '',
    country: '',
    place: '',
    industry: null,
    rationale: '',
    blocked: false,
    posted: null,
    first_seen: '2026-07-01T00:00:00Z',
    status: 'open',
    last_seen: '',
    closed_at: '',
    posted_age_days: null,
    stale: false,
    remote_mismatch: false,
    sources: [],
    coverage_pct: null,
    enrich: {},
    brief: '',
    description: '',
    contacts: [],
    recruiter: null,
    ...over,
  }
}

export function application(over: Partial<Application> & Pick<Application, 'job_id'>): Application {
  return {
    job_id: over.job_id,
    company: 'Acme',
    title: 'Engineer',
    status: 'applied',
    applied_at: '2026-07-01T00:00:00Z',
    updated: '2026-07-01T00:00:00Z',
    source: '',
    interview_at: '',
    salary_offered: '',
    offer_accepted: '',
    timeline: [],
    ...over,
  }
}

export function review(over: Partial<JobReview> & Pick<JobReview, 'job_id'>): JobReview {
  return {
    job_id: over.job_id,
    state: 'pending',
    origins: ['monitored'],
    monitor_ids: [],
    first_seen: '2026-07-01T00:00:00Z',
    reviewed_at: '',
    ...over,
  }
}

export function monitoredCompany(
  over: Partial<MonitoredCompany> & Pick<MonitoredCompany, 'id' | 'company'>,
): MonitoredCompany {
  return {
    id: over.id,
    company: over.company,
    provider: 'greenhouse',
    slug: over.company.toLowerCase(),
    careers_url: '',
    status: 'active',
    resolution_status: 'resolved',
    added_from: ['user'],
    checked_at: '',
    last_success_at: '',
    health_status: 'ok',
    health_detail: '',
    board_count: 0,
    open_matches: 0,
    pending_count: 0,
    saved_count: 0,
    contact_domain: '',
    contacts_checked_at: '',
    recruiter_count: 0,
    recruiter: null,
    ...over,
  }
}

export function dashboard(over: Partial<DashboardData> = {}): DashboardData {
  return {
    generated: '2026-07-08T00:00:00Z',
    total: 0,
    rows: [],
    overview: { funnel: {}, gaps: [], considered: 0, targets: [] },
    applications: [],
    profile: null,
    applied_outreach: [],
    companies: [],
    reviews: [],
    activity_audit: {
      recent_runs: [],
      selected_run_id: '',
      decisions: [],
      recoverable_applications: [],
    },
    ...over,
  }
}
