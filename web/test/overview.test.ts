import { describe, expect, it } from 'vitest'
import { buildOverview } from '@/lib/overview'
import type { Application, DashboardData, JobRow } from '@/lib/schema'

function row(over: Partial<JobRow> & Pick<JobRow, 'id'>): JobRow {
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
    remote_mismatch: false,
    sources: [],
    coverage_pct: null,
    enrich: {},
    brief: '',
    description: '',
    contacts: [],
    ...over,
  }
}

function app(over: Partial<Application> & Pick<Application, 'job_id'>): Application {
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

function data(over: Partial<DashboardData> = {}): DashboardData {
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

const NOW = Date.parse('2026-07-08T00:00:00Z')

describe('buildOverview', () => {
  it('counts the fit-tier donut', () => {
    const model = buildOverview(
      data({
        total: 3,
        rows: [row({ id: 'a', tier: 'Strong' }), row({ id: 'b', tier: 'Good' }), row({ id: 'c', tier: 'Strong' })],
      }),
      NOW,
    )
    expect(model.tiers.total).toBe(3)
    expect(model.tiers.segs.find((s) => s.label === 'Strong')?.value).toBe(2)
  })

  it('builds a descending funnel from status + timeline signals', () => {
    const apps = [
      app({ job_id: '1', status: 'applied' }),
      app({ job_id: '2', status: 'interview' }),
      app({ job_id: '3', status: 'offer' }),
      app({
        job_id: '4',
        status: 'applied',
        timeline: [{ date: '', signal: 'assessment', subject: '', from: '', summary: '' }],
      }),
    ]
    const rows = [row({ id: 'a', tier: 'Strong' }), row({ id: 'b', tier: 'Good' }), row({ id: 'c', tier: 'Skip' })]
    const byKey = Object.fromEntries(
      buildOverview(data({ rows, applications: apps }), NOW).funnel.map((s) => [s.key, s.value]),
    )
    expect(byKey.applied).toBe(4)
    expect(byKey.interview).toBe(3) // interview + offer + assessment signal
    expect(byKey.offer).toBe(1)
    expect(byKey.qualified).toBeUndefined() // fits are shown in the donut, not the funnel
  })

  it('ranks top companies by count', () => {
    const rows = [
      row({ id: '1', company: 'Stripe' }),
      row({ id: '2', company: 'Stripe' }),
      row({ id: '3', company: 'Datadog' }),
    ]
    const model = buildOverview(data({ rows }), NOW)
    expect(model.companies[0]).toEqual(expect.objectContaining({ label: 'Stripe', value: 2 }))
  })

  it('bins scores into bands', () => {
    const rows = [row({ id: '1', score: 55 }), row({ id: '2', score: 72 }), row({ id: '3', score: 95 })]
    const byLabel = Object.fromEntries(
      buildOverview(data({ rows }), NOW).scores.map((b) => [b.label, b.value]),
    )
    expect(byLabel['<60']).toBe(1)
    expect(byLabel['70-79']).toBe(1)
    expect(byLabel['90+']).toBe(1)
  })

  it('buckets the weekly surfacing trend', () => {
    const rows = [
      row({ id: '1', first_seen: '2026-07-07T00:00:00Z' }),
      row({ id: '2', first_seen: '2026-07-06T00:00:00Z' }),
      row({ id: '3', first_seen: '2026-06-10T00:00:00Z' }),
    ]
    const model = buildOverview(data({ rows }), NOW)
    expect(model.trend).toHaveLength(8)
    expect(model.trend[model.trend.length - 1].value).toBe(2) // most recent 7 days
  })

  it('reports empty flags with no data', () => {
    const model = buildOverview(data(), NOW)
    expect(model.hasRoles).toBe(false)
    expect(model.hasApplications).toBe(false)
    expect(model.tiers.total).toBe(0)
  })
})
