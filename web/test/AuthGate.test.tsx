import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AuthGate } from '@/app/AuthGate'
import { UNLOCK_KEY } from '@/lib/unlock'
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
    ...over,
  }
}

function row(id: string): JobRow {
  return {
    id, title: 'Role', company: 'Acme', location: '', remote: false, remote_scope: '',
    url: '', source: '', score: 0, tier: 'Good', base: '', salary: '', size: '', funding: '',
    country: '', place: '', industry: null, rationale: '', blocked: false, posted: null,
    first_seen: '', status: 'open', last_seen: '', closed_at: '', posted_age_days: null, stale: false, remote_mismatch: false, sources: [], enrich: {}, brief: '',
    description: '', contacts: [],
  }
}

describe('AuthGate', () => {
  beforeEach(() => sessionStorage.clear())

  it('renders the app straight through when the baked build has rows (local/dev)', () => {
    render(
      <AuthGate baked={makeData({ rows: [row('a')] })} encrypted={null}>
        {(data) => <div>rows: {data.rows.length}</div>}
      </AuthGate>,
    )
    expect(screen.getByText('rows: 1')).toBeInTheDocument()
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
})
