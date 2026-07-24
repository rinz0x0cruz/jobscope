import { afterEach, describe, expect, it, vi } from 'vitest'
import { listEngagements } from '@/lib/campaigns'

afterEach(() => vi.unstubAllGlobals())

describe('campaign API client edge cases', () => {
  it('degrades a successful partial engagement payload to an empty list', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    }) as Response))

    await expect(listEngagements('private-token')).resolves.toEqual([])
  })

  it('surfaces a bounded server error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ error: 'could not load engagement activity' }),
    }) as Response))

    await expect(listEngagements('private-token')).rejects.toThrow(
      'could not load engagement activity',
    )
  })
})