// Shared factories for web unit tests. Not a test file itself (no `.test`), so
// vitest won't try to run it.

import type { Application, DashboardData, JobRow } from '@/lib/schema'

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
    enrich: {},
    brief: '',
    description: '',
    contacts: [],
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
    timeline: [],
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
    ...over,
  }
}
