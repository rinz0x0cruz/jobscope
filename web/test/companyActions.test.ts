import { beforeEach, describe, expect, it, vi } from 'vitest'
import { acknowledgeMonitoringActions, collapseMonitoringActions, MONITORING_QUEUE_KEY, projectMonitoringActions, queuedMonitoringActions, submitMonitoringActions } from '@/lib/companyActions'
import { application, dashboard, jobRow, monitoredCompany, review } from './factories'

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

  it('promotes a known company optimistically without changing its identity', () => {
    const known = monitoredCompany({
      id: 'known-google', company: 'Google Inc.', lifecycle: 'known', status: 'removed',
      added_from: ['application'], provider: '', slug: '', resolution_status: 'unresolved',
    })

    const projected = projectMonitoringActions(dashboard({ companies: [known] }), [{
      type: 'monitor.upsert', company: 'Google', careers_url: '',
    }])

    expect(projected.companies).toHaveLength(1)
    expect(projected.companies[0]).toMatchObject({
      id: 'known-google', lifecycle: 'watching', status: 'active',
      added_from: ['application', 'user'],
    })
  })

  it('preserves a paused monitor during a generic upsert', () => {
    const paused = monitoredCompany({
      id: 'paused-acme', company: 'Acme', status: 'paused', lifecycle: 'watching',
    })

    const projected = projectMonitoringActions(dashboard({ companies: [paused] }), [{
      type: 'monitor.upsert', company: 'Acme', careers_url: 'https://acme.example/careers',
    }])

    expect(projected.companies[0]).toMatchObject({
      id: 'paused-acme', status: 'paused', lifecycle: 'watching',
      careers_url: 'https://acme.example/careers',
    })
  })

  it('demotes a removed watched company with application history to known', () => {
    const watched = monitoredCompany({ id: 'google', company: 'Google' })
    const data = dashboard({
      companies: [watched],
      applications: [application({ job_id: 'google-role', company: 'Google' })],
    })

    const projected = projectMonitoringActions(data, [{
      type: 'monitor.status', monitor_id: 'google', status: 'removed',
    }])

    expect(projected.companies[0]).toMatchObject({
      id: 'google', status: 'removed', lifecycle: 'known',
    })
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

  it('discards deprecated application restore actions from the local queue', () => {
    const saved = { type: 'review.set', job_id: 'a', state: 'saved' } as const
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify([
      { type: 'application.restore', job_id: 'mail:one' },
      saved,
    ]))

    expect(queuedMonitoringActions()).toEqual([saved])
  })
})