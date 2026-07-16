import { describe, expect, it } from 'vitest'
import { buildBriefing } from '@/lib/briefing'
import { buildTriage } from '@/lib/triage'
import { buildTimeline } from '@/lib/timeline'
import type { Application, DashboardData, JobRow } from '@/lib/schema'

const NOW = Date.parse('2026-07-01T00:00:00Z')
const DAY = 86_400_000
const ago = (days: number) => new Date(NOW - days * DAY).toISOString()

function makeData(over: Partial<DashboardData> = {}): DashboardData {
  return {
    generated: '2026-07-01T00:00:00Z',
    total: 0,
    rows: [],
    overview: { funnel: {}, gaps: [], considered: 0, targets: [] },
    applications: [],
    profile: null,
    applied_outreach: [],
    ...over,
  }
}

function row(over: Partial<JobRow> & Pick<JobRow, 'id'>): JobRow {
  return {
    title: 'Engineer', company: 'Acme', location: 'Remote', remote: true, remote_scope: '',
    url: 'https://x', source: 'x', score: 50, tier: 'Good', base: '', salary: '', size: '',
    funding: '', country: '', place: '', industry: null, rationale: 'good fit', blocked: false,
    posted: null, first_seen: ago(1), status: 'open', last_seen: '', closed_at: '', posted_age_days: null, stale: false, remote_mismatch: false, sources: [], coverage_pct: null, enrich: {},
    brief: '', description: '', contacts: [], ...over,
  }
}

function app(over: Partial<Application> & Pick<Application, 'job_id'>): Application {
  return {
    company: 'Acme', title: 'Engineer', status: 'applied', applied_at: ago(2), updated: ago(2),
    source: 'x', timeline: [], ...over,
  }
}

describe('buildBriefing', () => {
  const data = makeData({
    total: 12,
    applications: [
      app({ job_id: 'o', company: 'Globex', status: 'offer' }),
      app({ job_id: 'd', company: 'Initech', status: 'applied', applied_at: ago(10) }),
      app({ job_id: 'r', company: 'Umbrella', status: 'applied', applied_at: ago(2) }),
    ],
    rows: [row({ id: 'm', company: 'Stripe', tier: 'Strong', score: 92 })],
  })
  const b = buildBriefing(data, NOW)

  it('leads the headline with the strongest signal and flags what needs you', () => {
    expect(b.headline).toContain('offer')
    expect(b.headline.toLowerCase()).toContain('need')
  })
  it('reports the figures that matter', () => {
    const fig = Object.fromEntries(b.figures.map((f) => [f.key, f.value]))
    expect(fig.offers).toBe(1)
    expect(fig.needs).toBeGreaterThanOrEqual(1)
  })
  it('lists what moved this week and what needs a nudge', () => {
    expect(b.moved.some((m) => m.text.startsWith('Applied to Umbrella'))).toBe(true)
    expect(b.needs.some((n) => n.text.startsWith('Nudge Initech'))).toBe(true)
  })
  it('surfaces fresh strong matches worth a look', () => {
    expect(b.matches.map((m) => m.jobId)).toContain('m')
  })
})

describe('buildTriage', () => {
  it('queues open, non-skip, un-applied roles by score with a brief', () => {
    const data = makeData({
      rows: [
        row({ id: 'hi', score: 90, brief: 'strong match' }),
        row({ id: 'lo', score: 40, rationale: 'fallback reason' }),
        row({ id: 'skip', score: 99, tier: 'Skip' }),
        row({ id: 'closed', score: 95, status: 'closed' }),
        row({ id: 'done', score: 88 }),
      ],
      applications: [app({ job_id: 'done' })],
    })
    const q = buildTriage(data, NOW)
    expect(q.items.map((i) => i.jobId)).toEqual(['hi', 'lo'])
    expect(q.items[1].brief).toBe('fallback reason')
    expect(q.total).toBe(2)
  })
})

describe('buildTimeline', () => {
  const data = makeData({
    applications: [
      app({
        job_id: 'a', company: 'Acme', status: 'interview', applied_at: ago(5),
        timeline: [{ date: ago(1), signal: 'interview', subject: '', from: '', summary: '' }],
      }),
      app({ job_id: 'g', company: 'Initech', status: 'applied', applied_at: ago(10) }),
    ],
  })
  const t = buildTimeline(data, NOW)

  it('buckets history newest-first and labels signals', () => {
    expect(t.groups.some((g) => g.label === 'This week')).toBe(true)
    const texts = t.groups.flatMap((g) => g.events.map((e) => e.text))
    expect(texts).toContain('Interview step with Acme')
    expect(texts).toContain('Applied to Acme')
  })
  it('builds an agenda of follow-ups that need action', () => {
    expect(t.agenda.some((x) => x.text.startsWith('Follow up with Initech'))).toBe(true)
  })
  it('keeps same-day signals uniquely addressable', () => {
    const repeated = makeData({
      applications: [
        app({
          job_id: 'same-day', company: 'Acme', status: 'applied', applied_at: ago(5),
          timeline: [
            { date: ago(1), signal: 'confirmation', subject: 'First', from: '', summary: '' },
            { date: ago(1), signal: 'confirmation', subject: 'Second', from: '', summary: '' },
          ],
        }),
      ],
    })
    const ids = buildTimeline(repeated, NOW).groups.flatMap((group) => group.events.map((event) => event.id))
    expect(new Set(ids).size).toBe(ids.length)
  })
})
