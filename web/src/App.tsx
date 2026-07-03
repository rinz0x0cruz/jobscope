import { useMemo, useState } from 'react'
import { dashboard } from '@/data'
import type { Tier } from '@/lib/schema'
import { TIERS } from '@/lib/schema'
import { fmtGenerated } from '@/lib/format'
import { Header } from '@/components/Header'
import { Kpis } from '@/components/Kpis'
import { JobList } from '@/components/JobList'

const FILTERS: (Tier | 'All')[] = ['All', ...TIERS]

export default function App() {
  const [query, setQuery] = useState('')
  const [tier, setTier] = useState<Tier | 'All'>('All')

  const rows = dashboard.rows

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((r) => {
      if (tier !== 'All' && r.tier !== tier) return false
      if (!q) return true
      return (
        r.title.toLowerCase().includes(q) ||
        r.company.toLowerCase().includes(q) ||
        r.place.toLowerCase().includes(q)
      )
    })
  }, [rows, query, tier])

  return (
    <div className="min-h-screen">
      <Header
        total={rows.length}
        shown={filtered.length}
        generated={fmtGenerated(dashboard.generated)}
        query={query}
        onQuery={setQuery}
      />
      <main className="mx-auto flex max-w-5xl flex-col gap-5 px-6 py-6">
        <Kpis rows={rows} />

        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              type="button"
              key={f}
              onClick={() => setTier(f)}
              className={
                'rounded-full border px-3 py-1.5 text-[13px] transition ' +
                (tier === f
                  ? 'border-accent bg-accent-dim text-accent'
                  : 'border-border bg-card text-dim hover:border-border-h hover:text-fg')
              }
            >
              {f}
            </button>
          ))}
        </div>

        <JobList rows={filtered} />
      </main>
    </div>
  )
}
