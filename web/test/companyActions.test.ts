import { beforeEach, describe, expect, it, vi } from 'vitest'
import { acknowledgeMonitoringActions, collapseMonitoringActions, MONITORING_QUEUE_KEY, projectMonitoringActions, queuedMonitoringActions, submitMonitoringActions } from '@/lib/companyActions'
import { dashboard, jobRow, monitoredCompany, review } from './factories'

describe('company actions', () => {
  beforeEach(() => localStorage.clear())

  it('collapses repeated entity decisions to the final action', () => {
    expect(collapseMonitoringActions([
      { type: 'review.set', job_id: 'a', state: 'saved' },
      { type: 'review.set', job_id: 'a', state: 'dismissed' },
      { type: 'monitor.status', monitor_id: 'm', status: 'paused' },
    ])).toEqual([
      { type: 'review.set', job_id: 'a', state: 'dismissed' },
      { type: 'monitor.status', monitor_id: 'm', status: 'paused' },
    ])
  })

  it('projects review, monitor, and queued-company actions optimistically', () => {
    const data = dashboard({
      rows: [jobRow({ id: 'a' })],
      reviews: [review({ job_id: 'a' })],
      companies: [monitoredCompany({ id: 'm', company: 'Acme' })],
    })
    const projected = projectMonitoringActions(data, [
      { type: 'review.set', job_id: 'a', state: 'saved' },
      { type: 'monitor.status', monitor_id: 'm', status: 'paused' },
      { type: 'monitor.upsert', company: 'Beta', careers_url: 'https://beta.example/careers' },
    ])
    expect(projected.reviews[0].state).toBe('saved')
    expect(projected.companies.find((company) => company.id === 'm')?.status).toBe('paused')
    expect(projected.companies.find((company) => company.company === 'Beta')?.health_detail).toBe('Queued for sync')
  })

  it('queues actions when local serve is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const result = await submitMonitoringActions([
      { type: 'review.set', job_id: 'a', state: 'saved' },
    ])
    expect(result.mode).toBe('queued')
    expect(queuedMonitoringActions()).toHaveLength(1)
    vi.unstubAllGlobals()
  })

  it('acknowledges only unchanged actions from the completed sync', () => {
    const saved = { type: 'review.set', job_id: 'a', state: 'saved' } as const
    const newer = { type: 'review.set', job_id: 'a', state: 'dismissed' } as const
    const added = { type: 'review.set', job_id: 'b', state: 'saved' } as const
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify([newer, added]))

    acknowledgeMonitoringActions([saved])

    expect(queuedMonitoringActions()).toEqual([newer, added])
  })
})