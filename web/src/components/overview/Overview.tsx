import type { ReactNode } from 'react'
import type { JobRow, Overview as OverviewStats } from '@/lib/schema'
import { funnelBars, tierSegments, topCompanies, topMatches } from '@/lib/overview'
import { Donut } from './Donut'
import { Bars } from './Bars'
import { SkillConstellation } from './SkillConstellation'
import { TopMatches } from './TopMatches'

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="rounded-[14px] border border-border bg-card p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <span className="text-xs text-mute">{subtitle}</span>}
      </div>
      {children}
    </section>
  )
}

export function Overview({ rows, stats, onOpen }: { rows: JobRow[]; stats: OverviewStats; onOpen: (id: string) => void }) {
  const { segs, total } = tierSegments(rows)
  const companies = topCompanies(rows, 8)
  const gaps = (stats.gaps ?? []).map(([label, value]) => ({ label, value }))
  const funnel = funnelBars(stats.funnel ?? {})
  const matches = topMatches(rows, 25)

  return (
    <div className="flex flex-col gap-4">
      {(stats.considered > 0 || (stats.targets?.length ?? 0) > 0) && (
        <p className="text-[13px] text-mute">
          Analyzed <span className="tnum text-fg">{stats.considered}</span> roles
          {stats.targets?.length ? <> · targeting {stats.targets.slice(0, 6).join(', ')}</> : null}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Fit distribution">
          <Donut segs={segs} total={total} />
        </Card>
        <Card title="Application pipeline">
          {funnel.length > 0 ? (
            <Bars items={funnel} color="var(--good)" />
          ) : (
            <div className="grid min-h-28 place-items-center text-center text-[13px] text-mute">
              No applications tracked yet — mark roles as applied to build your funnel.
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Top companies">
          <Bars items={companies} />
        </Card>
        <Card title="Skill gaps in your matches" subtitle="most in-demand">
          {gaps.length > 0 ? (
            <SkillConstellation items={gaps} />
          ) : (
            <div className="grid min-h-28 place-items-center text-[13px] text-mute">Not enough data.</div>
          )}
        </Card>
      </div>

      <Card title="Top matches" subtitle="click a role to open">
        <TopMatches rows={matches} onOpen={onOpen} />
      </Card>
    </div>
  )
}
