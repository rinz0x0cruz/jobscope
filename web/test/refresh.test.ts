import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock sonner so toasts are inert spies we can assert on.
vi.mock('sonner', () => {
  const toast = Object.assign(vi.fn(), {
    loading: vi.fn(() => 'toast-id'),
    success: vi.fn(),
    error: vi.fn(),
    dismiss: vi.fn(),
  })
  return { toast }
})

import { toast } from 'sonner'
import {
  scanCooldownRemaining,
  hasGitHubToken,
  connectToken,
  disconnectToken,
  scanNewMail,
  pullLatestData,
  GH_TOKEN_KEY,
  SCAN_COOLDOWN_MS,
  syncMonitoringQueue,
} from '@/lib/refresh'
import { MONITORING_QUEUE_KEY } from '@/lib/companyActions'

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

// Feature: 1-tap GitHub token (stored only in-browser) for direct dispatch.
describe('refresh: token connect / disconnect', () => {
  it('hasGitHubToken reflects the stored token', () => {
    expect(hasGitHubToken()).toBe(false)
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_x')
    expect(hasGitHubToken()).toBe(true)
  })

  it('connectToken stores a prompted, trimmed token; disconnect clears it', () => {
    vi.stubGlobal('prompt', vi.fn(() => '  ghp_secret  '))
    connectToken()
    expect(localStorage.getItem(GH_TOKEN_KEY)).toBe('ghp_secret')
    disconnectToken()
    expect(localStorage.getItem(GH_TOKEN_KEY)).toBeNull()
  })

  it('connectToken ignores an empty prompt', () => {
    vi.stubGlobal('prompt', vi.fn(() => '   '))
    connectToken()
    expect(localStorage.getItem(GH_TOKEN_KEY)).toBeNull()
  })
})

// Feature: anti-throttle cooldown so rapid taps never stack workflow runs.
describe('refresh: scan cooldown', () => {
  it('is 0 before any scan', () => {
    expect(scanCooldownRemaining()).toBe(0)
  })

  it('sets a cooldown after a scan and blocks an immediate re-trigger', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)

    await scanNewMail() // no token -> opens GitHub Run-workflow page + marks scanned
    expect(open).toHaveBeenCalledOnce()

    const remaining = scanCooldownRemaining()
    expect(remaining).toBeGreaterThan(0)
    expect(remaining).toBeLessThanOrEqual(SCAN_COOLDOWN_MS)

    open.mockClear()
    await scanNewMail() // on cooldown -> must NOT open GitHub again
    expect(open).not.toHaveBeenCalled()
  })
})

// Feature: direct workflow_dispatch when a token is connected, with run de-dupe.
describe('refresh: scanNewMail dispatch (token path)', () => {
  it('prefers the local guarded refresh endpoint when jobscope serve is available', async () => {
    const fetchMock = vi.fn(async (url: string, opts?: { method?: string }) => {
      if (url.endsWith('/api/token')) {
        return { ok: true, status: 200, json: async () => ({ token: 'local-token' }) } as Response
      }
      if (url.endsWith('/api/refresh') && opts?.method === 'POST') {
        return { ok: true, status: 200, json: async () => ({ state: 'started' }) } as Response
      }
      throw new Error(`unexpected URL: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    await scanNewMail()

    const refreshCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/refresh'))
    expect(refreshCall).toBeTruthy()
    expect(JSON.parse(String((refreshCall?.[1] as RequestInit).body))).toEqual({
      force: true, full_scan: false,
    })
    expect(toast.success).toHaveBeenCalledWith('Gmail scan started')
  })

  it('reloads live local data after a completed refresh', async () => {
    vi.useFakeTimers()
    const onData = vi.fn()
    const data = {
      generated: '2026-07-18T00:00:00', total: 0, rows: [],
      overview: { funnel: {}, gaps: [], considered: 0, targets: [] },
      applications: [], profile: null, applied_outreach: [], companies: [], reviews: [],
      activity_audit: { recent_runs: [], selected_run_id: '', decisions: [], recoverable_applications: [] },
    }
    vi.stubGlobal('fetch', vi.fn(async (url: string, opts?: { method?: string }) => {
      if (url.endsWith('/api/token')) return { ok: true, json: async () => ({ token: 'local-token' }) } as Response
      if (url.endsWith('/api/refresh') && opts?.method === 'POST') {
        return { ok: true, json: async () => ({ state: 'started' }) } as Response
      }
      if (url.endsWith('/api/status')) return { ok: true, json: async () => ({ state: 'done' }) } as Response
      if (url.endsWith('/api/dashboard')) {
        return { ok: true, json: async () => ({ ok: true, data }) } as Response
      }
      throw new Error(`unexpected URL: ${url}`)
    }))

    await scanNewMail(onData)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.waitFor(() => expect(onData).toHaveBeenCalledWith(data))
  })

  it('checks for a running run, then POSTs workflow_dispatch', async () => {
    vi.useFakeTimers() // freeze the post-dispatch poll timer
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')

    const fetchMock = vi.fn(async (_url: string, opts?: { method?: string }) => {
      if (opts?.method === 'POST') return { status: 204 } as Response
      return { ok: true, status: 200, json: async () => ({ workflow_runs: [] }) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await scanNewMail()

    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls.some((u) => u.includes('/actions/workflows/refresh.yml/runs'))).toBe(true)

    const post = fetchMock.mock.calls.find((c) => (c[1] as { method?: string })?.method === 'POST')
    expect(post).toBeTruthy()
    expect(String(post![0])).toContain('/dispatches')
    expect(toast.success).toHaveBeenCalled()
  })

  it('does not dispatch when a run is already active (de-dupe)', async () => {
    vi.useFakeTimers()
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')

    const fetchMock = vi.fn(async (_url: string, opts?: { method?: string }) => {
      if (opts?.method === 'POST') return { status: 204 } as Response
      return { ok: true, status: 200, json: async () => ({ workflow_runs: [{ status: 'in_progress', conclusion: null }] }) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await scanNewMail()

    const posted = fetchMock.mock.calls.some((c) => (c[1] as { method?: string })?.method === 'POST')
    expect(posted).toBe(false) // never POSTs a dispatch on top of an active run
  })
})

describe('refresh: queued monitoring changes', () => {
  const queued = [{ type: 'review.set', job_id: 'job-1', state: 'saved' }]

  it('dispatches one workflow input for the collapsed queue', async () => {
    vi.useFakeTimers()
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify(queued))
    const fetchMock = vi.fn(async (_url: string, opts?: { method?: string }) => {
      if (opts?.method === 'POST') return { status: 204 } as Response
      return { ok: true, status: 200, json: async () => ({ workflow_runs: [] }) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await syncMonitoringQueue()

    const post = fetchMock.mock.calls.find((call) => (call[1] as { method?: string })?.method === 'POST')
    const body = JSON.parse(String((post![1] as RequestInit).body))
    expect(JSON.parse(body.inputs.mutations_json)).toEqual(queued)
    expect(localStorage.getItem(MONITORING_QUEUE_KEY)).not.toBeNull()
  })

  it('keeps the queue when another refresh is active', async () => {
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify(queued))
    const fetchMock = vi.fn(async () => ({
      ok: true, status: 200,
      json: async () => ({ workflow_runs: [{ status: 'in_progress', conclusion: null }] }),
    }) as unknown as Response)
    vi.stubGlobal('fetch', fetchMock)

    await syncMonitoringQueue()

    expect(fetchMock.mock.calls.some((call) => (call[1] as { method?: string })?.method === 'POST')).toBe(false)
    expect(localStorage.getItem(MONITORING_QUEUE_KEY)).not.toBeNull()
  })

  it('clears the queue only after the dispatched run succeeds', async () => {
    vi.useFakeTimers()
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify(queued))
    let runChecks = 0
    let expectedTitle = ''
    const fetchMock = vi.fn(async (_url: string, opts?: { method?: string; body?: BodyInit | null }) => {
      if (opts?.method === 'POST') {
        const body = JSON.parse(String(opts.body))
        expectedTitle = `Monitoring sync ${body.inputs.mutation_nonce}`
        return { status: 204 } as Response
      }
      runChecks += 1
      return {
        ok: true, status: 200,
        json: async () => ({ workflow_runs: runChecks === 1 ? [] : [{
          status: 'completed', conclusion: 'success', display_title: expectedTitle,
        }] }),
      } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await syncMonitoringQueue()
    expect(localStorage.getItem(MONITORING_QUEUE_KEY)).not.toBeNull()
    await vi.advanceTimersByTimeAsync(6500)
    expect(localStorage.getItem(MONITORING_QUEUE_KEY)).toBeNull()
  })

  it('ignores an older successful refresh while waiting for its mutation run', async () => {
    vi.useFakeTimers()
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify(queued))
    let runChecks = 0
    let expectedTitle = ''
    const oldRun = {
      status: 'completed', conclusion: 'success', display_title: 'Refresh (schedule)',
    }
    const fetchMock = vi.fn(async (_url: string, opts?: { method?: string; body?: BodyInit | null }) => {
      if (opts?.method === 'POST') {
        const body = JSON.parse(String(opts.body))
        expectedTitle = `Monitoring sync ${body.inputs.mutation_nonce}`
        return { status: 204 } as Response
      }
      runChecks += 1
      return {
        ok: true, status: 200,
        json: async () => ({ workflow_runs: runChecks < 3 ? [oldRun] : [
          { status: 'completed', conclusion: 'success', display_title: expectedTitle },
          oldRun,
        ] }),
      } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await syncMonitoringQueue()
    await vi.advanceTimersByTimeAsync(6500)
    expect(localStorage.getItem(MONITORING_QUEUE_KEY)).not.toBeNull()
    await vi.advanceTimersByTimeAsync(12500)
    expect(localStorage.getItem(MONITORING_QUEUE_KEY)).toBeNull()
  })

  it('preserves decisions queued after the dispatched snapshot', async () => {
    vi.useFakeTimers()
    localStorage.setItem(GH_TOKEN_KEY, 'ghp_token')
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify(queued))
    let expectedTitle = ''
    const fetchMock = vi.fn(async (_url: string, opts?: { method?: string; body?: BodyInit | null }) => {
      if (opts?.method === 'POST') {
        const body = JSON.parse(String(opts.body))
        expectedTitle = `Monitoring sync ${body.inputs.mutation_nonce}`
        return { status: 204 } as Response
      }
      return {
        ok: true, status: 200,
        json: async () => ({ workflow_runs: expectedTitle ? [{
          status: 'completed', conclusion: 'success', display_title: expectedTitle,
        }] : [] }),
      } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await syncMonitoringQueue()
    const later = { type: 'review.set', job_id: 'job-2', state: 'dismissed' }
    localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify([...queued, later]))
    await vi.advanceTimersByTimeAsync(6500)

    expect(JSON.parse(localStorage.getItem(MONITORING_QUEUE_KEY) || '[]')).toEqual([later])
  })
})

// Feature: pull the freshest published build via the service worker.
describe('refresh: pullLatestData', () => {
  it('asks the service worker to update', async () => {
    vi.useFakeTimers()
    const update = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', {
      serviceWorker: {
        getRegistration: vi.fn().mockResolvedValue({ update, waiting: null }),
        addEventListener: vi.fn(),
      },
    })

    await pullLatestData()

    expect(toast.loading).toHaveBeenCalled()
    expect(update).toHaveBeenCalled()
  })
})
