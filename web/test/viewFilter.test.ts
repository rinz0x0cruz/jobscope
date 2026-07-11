import { describe, expect, it } from 'vitest'
import { filterData } from '@/lib/viewFilter'
import { application, dashboard, jobRow } from './factories'

describe('filterData', () => {
  it('returns the data unchanged for an empty query', () => {
    const d = dashboard({ rows: [jobRow({ id: 'a' })] })
    expect(filterData(d, '')).toBe(d)
    expect(filterData(d, '   ')).toBe(d)
  })

  it('narrows rows by company, title, or location', () => {
    const d = dashboard({
      total: 3,
      rows: [
        jobRow({ id: 'a', company: 'Stripe', title: 'SRE' }),
        jobRow({ id: 'b', company: 'Globex', title: 'Detection Engineer' }),
        jobRow({ id: 'c', company: 'Globex', title: 'SRE', location: 'Berlin' }),
      ],
    })
    expect(filterData(d, 'stripe').rows.map((r) => r.id)).toEqual(['a'])
    expect(filterData(d, 'detection').rows.map((r) => r.id)).toEqual(['b'])
    expect(filterData(d, 'berlin').rows.map((r) => r.id)).toEqual(['c'])
  })

  it('narrows applications and recomputes total', () => {
    const d = dashboard({
      total: 2,
      rows: [jobRow({ id: 'a', company: 'Stripe' }), jobRow({ id: 'b', company: 'Globex' })],
      applications: [
        application({ job_id: 'a', company: 'Stripe' }),
        application({ job_id: 'b', company: 'Globex' }),
      ],
    })
    const v = filterData(d, 'stripe')
    expect(v.total).toBe(1)
    expect(v.rows.map((r) => r.id)).toEqual(['a'])
    expect(v.applications?.map((a) => a.job_id)).toEqual(['a'])
  })

  it('is case-insensitive', () => {
    const d = dashboard({ rows: [jobRow({ id: 'a', company: 'OpenAI' })] })
    expect(filterData(d, 'OPENAI').rows).toHaveLength(1)
  })
})
