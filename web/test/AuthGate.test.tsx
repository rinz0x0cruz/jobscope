import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AuthGate } from '@/app/AuthGate'
import { UNLOCK_KEY } from '@/lib/unlock'
import { resetLocalServeToken } from '@/lib/outreach'
import type { DashboardData, JobRow } from '@/lib/schema'

function makeData(over: Partial<DashboardData> = {}): DashboardData {
  return {
    generated: '',
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

function row(id: string): JobRow {
  return {
    id, title: 'Role', company: 'Acme', location: '', remote: false, remote_scope: '',
    url: '', source: '', score: 0, tier: 'Good', base: '', salary: '', size: '', funding: '',
    country: '', place: '', industry: null, rationale: '', blocked: false, posted: null,
    first_seen: '', status: 'open', last_seen: '', closed_at: '', posted_age_days: null, stale: false, remote_mismatch: false, sources: [], coverage_pct: null, enrich: {}, brief: '',
    description: '', contacts: [],
  }
}

describe('AuthGate', () => {
  beforeEach(() => {
    sessionStorage.clear()
    resetLocalServeToken()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the app straight through when the baked build has rows (local/dev)', () => {
    render(
      <AuthGate baked={makeData({ rows: [row('a')] })} encrypted={null}>
        {(data) => <div>rows: {data.rows.length}</div>}
      </AuthGate>,
    )
    expect(screen.getByText('rows: 1')).toBeInTheDocument()
  })

  it('replaces baked startup data with the live local dashboard', async () => {
    const live = makeData({
      generated: 'live',
      total: 2,
      rows: [row('live-a'), row('live-b')],
    })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/api/token')) {
        return { ok: true, json: async () => ({ token: 'local-token' }) } as Response
      }
      if (url.endsWith('/api/dashboard')) {
        return { ok: true, json: async () => ({ ok: true, data: live }) } as Response
      }
      throw new Error(`unexpected URL: ${url}`)
    }))
    render(
      <AuthGate baked={makeData({ rows: [row('baked')] })} encrypted={null}>
        {(data) => <div>rows: {data.rows.length}</div>}
      </AuthGate>,
    )
    expect(screen.getByText('rows: 1')).toBeInTheDocument()
    expect(await screen.findByText('rows: 2')).toBeInTheDocument()
  })

  it('locks the app and shows the passphrase form when the baked build is empty', () => {
    render(
      <AuthGate baked={makeData()} encrypted={{ v: 1, url: 'site.enc.json' }}>
        {() => <div>secret content</div>}
      </AuthGate>,
    )
    expect(screen.getByText('This dashboard is locked')).toBeInTheDocument()
    expect(screen.getByLabelText('Passphrase')).toBeInTheDocument()
    expect(screen.queryByText('secret content')).not.toBeInTheDocument()
  })

  it('renders from a cached unlock without prompting for a passphrase', () => {
    sessionStorage.setItem(UNLOCK_KEY, JSON.stringify(makeData({ rows: [row('x'), row('y')] })))
    render(
      <AuthGate baked={makeData()} encrypted={{ v: 1, url: 'site.enc.json' }}>
        {(data) => <div>unlocked rows: {data.rows.length}</div>}
      </AuthGate>,
    )
    expect(screen.getByText('unlocked rows: 2')).toBeInTheDocument()
    expect(screen.queryByLabelText('Passphrase')).not.toBeInTheDocument()
  })

  it('shows a no-data message when locked with no encrypted blob', () => {
    render(
      <AuthGate baked={makeData()} encrypted={null}>
        {() => <div>nope</div>}
      </AuthGate>,
    )
    expect(screen.getByText(/No encrypted data/i)).toBeInTheDocument()
  })

  it('does not probe the local API from a public static origin', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('location', new URL('https://rinz0x0cruz.github.io/jobscope/'))

    render(
      <AuthGate baked={makeData()} encrypted={{ v: 1, url: 'site.enc.json' }}>
        {() => <div>secret content</div>}
      </AuthGate>,
    )

    expect(screen.getByText('This dashboard is locked')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
