import { afterEach, describe, expect, it, vi } from 'vitest'
import { profileUpdate, resetLocalServeToken } from '@/lib/outreach'

afterEach(() => {
  resetLocalServeToken()
  vi.unstubAllGlobals()
})

describe('control-plane token recovery', () => {
  it('reprobes once and retries a guarded action after a stale-token 403', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const token = new Headers(init?.headers).get('X-Refresh-Token')
      if (url.endsWith('/api/token')) {
        return { ok: true, status: 200, json: async () => ({ token: 'fresh-token' }) } as Response
      }
      if (token === 'fresh-token') {
        return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response
      }
      return {
        ok: false, status: 403, json: async () => ({ ok: false, error: 'forbidden' }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(profileUpdate('research', 'stale-token', {
      search_terms: ['Security Engineer'], locations: ['Remote'], remote: true,
    })).resolves.toMatchObject({ ok: true })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('X-Refresh-Token'))
      .toBe('fresh-token')
  })
})