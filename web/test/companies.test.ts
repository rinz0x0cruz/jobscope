import { describe, expect, it } from 'vitest'
import { buildCompanies, monitorCheckAge } from '@/lib/companies'
import { dashboard, jobRow, monitoredCompany, review } from './factories'

describe('companies model', () => {
  it('formats monitor check timestamps for quick scanning', () => {
    const now = Date.parse('2026-07-17T12:00:00Z')
    expect(monitorCheckAge('', now)).toBe('not yet')
    expect(monitorCheckAge('2026-07-17T08:00:00Z', now)).toBe('today')
    expect(monitorCheckAge('2026-07-16T08:00:00Z', now)).toBe('yesterday')
    expect(monitorCheckAge('2026-07-12T08:00:00Z', now)).toBe('5d ago')
  })

  it('joins monitor jobs by durable review provenance', () => {
    const data = dashboard({
      companies: [monitoredCompany({ id: 'monitor-a', company: 'Acme', pending_count: 1, saved_count: 1 })],
      rows: [
        jobRow({ id: 'pending', company: 'Acme', score: 80 }),
        jobRow({ id: 'saved', company: 'Acme', score: 70 }),
      ],
      reviews: [
        review({ job_id: 'pending', monitor_ids: ['monitor-a'] }),
        review({ job_id: 'saved', state: 'saved', monitor_ids: ['monitor-a'] }),
      ],
    })

    const model = buildCompanies(data)

    expect(model.items[0].pendingJobs.map((job) => job.id)).toEqual(['pending'])
    expect(model.items[0].savedJobs.map((job) => job.id)).toEqual(['saved'])
    expect(model.items[0].pending_count).toBe(1)
    expect(model.items[0].saved_count).toBe(1)
  })

  it('keeps server review counts while freshly scanned rows are loading', () => {
    const data = dashboard({
      companies: [monitoredCompany({ id: 'monitor-a', company: 'Acme' })],
      reviews: [review({ job_id: 'new-job', monitor_ids: ['monitor-a'] })],
    })

    const [company] = buildCompanies(data).items

    expect(company.pending_count).toBe(1)
    expect(company.pendingJobs).toEqual([])
  })

  it('counts monitor states and searches company/provider/slug', () => {
    const data = dashboard({
      companies: [
        monitoredCompany({ id: 'a', company: 'Acme' }),
        monitoredCompany({ id: 'b', company: 'Beta', status: 'paused', provider: 'lever' }),
        monitoredCompany({ id: 'c', company: 'Gamma', resolution_status: 'unresolved', provider: '', slug: '' }),
      ],
    })
    const model = buildCompanies(data, 'lever')
    expect(model.items.map((company) => company.company)).toEqual(['Beta'])
    expect(model.active).toBe(2)
    expect(model.paused).toBe(1)
    expect(model.needsSetup).toBe(1)
  })
})