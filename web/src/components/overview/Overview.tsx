import { useMemo, useState, type ReactNode } from 'react'
import type { JobRow, Overview as OverviewStats } from '@/lib/schema'
import { funnelBars, tierSegments, topCompanies, topMatches } from '@/lib/overview'
import { trackSpotlight } from '@/lib/spotlight'
import { Donut } from './Donut'
import { Bars } from './Bars'
import { SkillConstellation } from './SkillConstellation'
import { TopMatches } from './TopMatches'

function Card({
  title,
  subtitle,
  children,
  className = '',
}: {
  title: string
  subtitle?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`js-gradient-card js-spotlight-card flex flex-col rounded-[14px] border border-border bg-card p-4 ${className}`}
      onPointerMove={trackSpotlight}
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <span className="text-xs text-mute">{subtitle}</span>}
      </div>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  )
}

function rowMentionsSkill(row: JobRow, skill: string): boolean {
  const needle = skill.trim().toLowerCase()
  if (!needle) return false
  const enrichNews = row.enrich.news?.map((item) => item.title || '').join(' ') ?? ''
  const haystack = [
    row.title,
    row.company,
    row.industry ?? '',
    row.brief,
    row.rationale,
    row.source,
    enrichNews,
  ].join(' ').toLowerCase()
  if (haystack.includes(needle)) return true
  const parts = needle.split(/[^a-z0-9+#.]+/).filter((part) => part.length > 1)
  return parts.length > 1 && parts.every((part) => haystack.includes(part))
}

export function Overview({ rows, stats, onOpen }: { rows: JobRow[]; stats: OverviewStats; onOpen: (id: string) => void }) {
  const { segs, total } = tierSegments(rows)
  const companies = topCompanies(rows, 8)
  const gaps = (stats.gaps ?? []).map(([label, value]) => ({ label, value }))
  const funnel = funnelBars(stats.funnel ?? {})
  const matches = topMatches(rows, 25)
  const [selectedSkill, setSelectedSkill] = useState('')
  const selectedGap = gaps.find((gap) => gap.label === selectedSkill)
  const skillRoles = useMemo(
    () => (selectedSkill ? topMatches(rows.filter((row) => rowMentionsSkill(row, selectedSkill)), 6) : []),
    [rows, selectedSkill],
  )

  return (
    <div className="flex flex-col gap-4">
      {(stats.considered > 0 || (stats.targets?.length ?? 0) > 0) && (
        <p className="text-[13px] text-mute">
          Analyzed <span className="tnum text-fg">{stats.considered}</span> roles
          {stats.targets?.length ? <> · targeting {stats.targets.slice(0, 6).join(', ')}</> : null}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-6">
        <Card title="Fit distribution" className="lg:col-span-2">
          <Donut segs={segs} total={total} />
        </Card>

        <Card title="Application pipeline" className="lg:col-span-2">
          {funnel.length > 0 ? (
            <Bars items={funnel} color="var(--good)" />
          ) : (
            <div className="grid min-h-28 flex-1 place-items-center text-center text-[13px] text-mute">
              No applications tracked yet — mark roles as applied to build your funnel.
            </div>
          )}
        </Card>

        <Card title="Top companies" className="lg:col-span-2">
          <Bars items={companies} />
        </Card>

        <Card
          title="Skill gaps in your matches"
          subtitle="most in-demand"
          className="lg:col-span-4 lg:row-span-2"
        >
          {gaps.length > 0 ? (
            <>
              <SkillConstellation items={gaps} selected={selectedSkill} onSelect={setSelectedSkill} />
              <div className="mt-3 rounded-[12px] border border-border bg-bg2/80 p-3">
                {selectedGap ? (
                  <>
                    <div className="mb-2 flex items-baseline justify-between gap-3">
                      <div>
                        <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-mute">Selected gap</div>
                        <div className="text-sm font-semibold text-fg">{selectedGap.label}</div>
                      </div>
                      <div className="text-right text-xs text-mute tnum">
                        {selectedGap.value} matched role{selectedGap.value === 1 ? '' : 's'}
                      </div>
                    </div>
                    {skillRoles.length > 0 ? (
                      <div className="flex flex-col gap-1.5">
                        {skillRoles.map((role) => (
                          <button
                            key={role.id}
                            type="button"
                            onClick={() => onOpen(role.id)}
                            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[9px] border border-border bg-card px-2.5 py-2 text-left text-[12.5px] transition hover:border-border-h hover:bg-card-h"
                          >
                            <span className="min-w-0 truncate text-fg">{role.title}</span>
                            <span className="text-mute tnum">{Math.round(role.score)}</span>
                            <span className="min-w-0 truncate text-mute">{role.company || '—'}</span>
                            <span className="text-xs text-dim">{role.tier}</span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[12.5px] text-mute">
                        No visible role text mentions this skill directly. It may come from description text that is not emitted in the public dashboard.
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-[12.5px] text-mute">Select a node to show roles that mention that gap.</div>
                )}
              </div>
            </>
          ) : (
            <div className="grid min-h-28 flex-1 place-items-center text-[13px] text-mute">Not enough data.</div>
          )}
        </Card>

        <Card
          title="Top matches"
          subtitle="click a role to open"
          className="lg:col-span-2 lg:row-span-2"
        >
          <TopMatches rows={matches} onOpen={onOpen} />
        </Card>
      </div>
    </div>
  )
}
