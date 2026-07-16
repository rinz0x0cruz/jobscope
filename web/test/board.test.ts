import { describe, expect, it } from 'vitest'
import { BOARD_STAGES, buildBoard, filterBoard } from '@/lib/board'
import type { Application, DashboardData } from '@/lib/schema'

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
    companies: [],
    reviews: [],
    ...over,
  }
}

function app(over: Partial<Application> & Pick<Application, 'job_id'>): Application {
  return {
    company: 'Acme',
    title: 'Engineer',
    status: 'applied',
    applied_at: ago(2),
    updated: ago(2),
    source: 'x',
    timeline: [],
    ...over,
  }
}

const col = (cols: ReturnType<typeof buildBoard>, stage: string) =>
  cols.find((c) => c.stage === stage)!

describe('buildBoard', () => {
  it('returns one column per board stage in canonical order', () => {
    const cols = buildBoard(makeData(), NOW)
    expect(cols.map((c) => c.stage)).toEqual([...BOARD_STAGES])
  })

  it('groups applications by pipeline status and drops skipped roles', () => {
    const data = makeData({
      applications: [
        app({ job_id: 'a', status: 'applied' }),
        app({ job_id: 'b', status: 'interview' }),
        app({ job_id: 'c', status: 'offer' }),
        app({ job_id: 'd', status: 'skipped' }),
      ],
    })
    const cols = buildBoard(data, NOW)
    expect(col(cols, 'applied').cards.map((c) => c.id)).toEqual(['a'])
    expect(col(cols, 'interview').cards.map((c) => c.id)).toEqual(['b'])
    expect(col(cols, 'offer').cards.map((c) => c.id)).toEqual(['c'])
    // 'd' (skipped) appears in no column.
    expect(cols.flatMap((c) => c.cards).some((c) => c.id === 'd')).toBe(false)
  })

  it('flags applications that have gone quiet as due / ghosted', () => {
    const data = makeData({
      applications: [
        app({ job_id: 'due', applied_at: ago(10) }),
        app({ job_id: 'ghost', applied_at: ago(30) }),
        app({ job_id: 'fresh', applied_at: ago(2) }),
      ],
    })
    const flags = Object.fromEntries(
      col(buildBoard(data, NOW), 'applied').cards.map((c) => [c.id, c.followup]),
    )
    expect(flags).toEqual({ due: 'due', ghost: 'ghosted', fresh: undefined })
  })

  it('marks cards whose company has ready HR outreach contacts', () => {
    const data = makeData({
      applications: [app({ job_id: 'a', company: 'Globex' })],
      applied_outreach: [
        {
          company: 'Globex',
          domain: 'globex.com',
          status: 'applied',
          applied_at: ago(2),
          contacts: [{ email: 'hr@globex.com', confidence: 'high', source: 'recruiter', note: '' }],
        },
      ],
    })
    expect(col(buildBoard(data, NOW), 'applied').cards[0].outreach).toBe(true)
  })
})

describe('filterBoard', () => {
  const base = buildBoard(
    makeData({
      applications: [
        app({ job_id: 'x', company: 'Stripe', title: 'Backend Engineer', status: 'applied' }),
        app({ job_id: 'y', company: 'Acme', title: 'Data Scientist', status: 'applied' }),
      ],
    }),
    NOW,
  )

  it('keeps only cards matching the query across company/title/location', () => {
    const filtered = filterBoard(base, 'stripe')
    expect(col(filtered, 'applied').cards.map((c) => c.id)).toEqual(['x'])
  })

  it('returns columns unchanged for an empty query', () => {
    expect(filterBoard(base, '   ')).toBe(base)
  })
})
