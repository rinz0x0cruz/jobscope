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
} from '@/lib/refresh'

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
