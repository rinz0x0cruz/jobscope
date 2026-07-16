import { describe, expect, it } from 'vitest'
import { buildFeed } from '@/lib/feed'
import { searchSchema } from '@/lib/urlState'
import { application, dashboard, jobRow, review } from './factories'

function state(over: Record<string, unknown> = {}) {
  return searchSchema.parse(over)
}

describe('feed model', () => {
  it('ranks open unapplied roles and excludes Skip and applied rows', () => {
    const data = dashboard({
      rows: [
        jobRow({ id: 'high', company: 'High', score: 90, tier: 'Strong' }),
        jobRow({ id: 'low', company: 'Low', score: 62, tier: 'Good' }),
        jobRow({ id: 'skip', company: 'Skip', score: 20, tier: 'Skip' }),
        jobRow({ id: 'applied', company: 'Applied', score: 95, tier: 'Strong' }),
      ],
      applications: [application({ job_id: 'applied' })],
      reviews: [review({ job_id: 'high' }), review({ job_id: 'low' })],
    })

    expect(buildFeed(data, state()).items.map((item) => item.row.id)).toEqual(['high', 'low'])
  })

  it('supports newest and company sorting', () => {
    const data = dashboard({
      rows: [
        jobRow({ id: 'z', company: 'Zulu', score: 90, first_seen: '2026-07-01' }),
        jobRow({ id: 'a', company: 'Acme', score: 60, first_seen: '2026-07-15' }),
      ],
      reviews: [review({ job_id: 'z' }), review({ job_id: 'a' })],
    })

    expect(buildFeed(data, state({ sort: 'newest' })).items[0].row.id).toBe('a')
    expect(buildFeed(data, state({ sort: 'company' })).items[0].row.id).toBe('a')
  })

  it('applies flags, facets, query, and tier selection together', () => {
    const data = dashboard({
      rows: [
        jobRow({
          id: 'match',
          company: 'Stripe',
          title: 'Security Engineer',
          tier: 'Strong',
          remote: true,
          salary: '$180k',
          country: 'India',
          contacts: [{ name: 'Jane', title: 'Recruiter', url: 'https://example.com' }],
          first_seen: '2026-07-15T00:00:00Z',
        }),
        jobRow({ id: 'other', company: 'Globex', tier: 'Good', remote: false, country: 'USA' }),
      ],
      reviews: [review({ job_id: 'match' }), review({ job_id: 'other' })],
    })

    const model = buildFeed(
      data,
      state({
        q: 'stripe',
        flags: ['remote', 'salary', 'referral', 'fresh'],
        tiers: ['Strong'],
        country: ['India'],
      }),
      Date.parse('2026-07-16T00:00:00Z'),
    )
    expect(model.items.map((item) => item.row.id)).toEqual(['match'])
  })

  it('honors legacy tier tabs while new tier state takes precedence', () => {
    const data = dashboard({
      rows: [
        jobRow({ id: 'strong', tier: 'Strong' }),
        jobRow({ id: 'good', tier: 'Good' }),
      ],
      reviews: [review({ job_id: 'strong' }), review({ job_id: 'good' })],
    })
    expect(buildFeed(data, state({ tab: 'Strong' })).items.map((item) => item.row.id)).toEqual(['strong'])
    expect(buildFeed(data, state({ tab: 'Strong', tiers: ['Good'] })).items.map((item) => item.row.id)).toEqual(['good'])
  })

  it('separates monitored, discovery, saved, and dismissed review buckets', () => {
    const data = dashboard({
      rows: [
        jobRow({ id: 'monitored' }),
        jobRow({ id: 'discovery' }),
        jobRow({ id: 'saved' }),
        jobRow({ id: 'dismissed' }),
        jobRow({ id: 'both' }),
      ],
      reviews: [
        review({ job_id: 'monitored' }),
        review({ job_id: 'discovery', origins: ['discovery'] }),
        review({ job_id: 'saved', state: 'saved', origins: ['discovery'] }),
        review({ job_id: 'dismissed', state: 'dismissed' }),
        review({ job_id: 'both', origins: ['discovery', 'monitored'] }),
      ],
    })

    expect(buildFeed(data, state()).items.map((item) => item.row.id).sort()).toEqual(['both', 'monitored'])
    expect(buildFeed(data, state({ reviewBucket: 'discovery' })).items.map((item) => item.row.id)).toEqual(['discovery'])
    expect(buildFeed(data, state({ reviewBucket: 'saved' })).items.map((item) => item.row.id)).toEqual(['saved'])
    expect(buildFeed(data, state({ reviewBucket: 'dismissed' })).items.map((item) => item.row.id)).toEqual(['dismissed'])
    expect(buildFeed(data, state()).buckets).toEqual({ monitored: 2, discovery: 1, saved: 1, dismissed: 1 })
  })
})
