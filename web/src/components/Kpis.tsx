import type { JobRow, Tier } from '@/lib/schema'
import { TIERS, TIER_COLOR } from '@/lib/schema'
import { CountUp } from './overview/CountUp'
import type { CSSProperties } from 'react'

export function Kpis({ rows }: { rows: JobRow[] }) {
  const counts: Record<Tier, number> = { Strong: 0, Good: 0, Stretch: 0, Skip: 0 }
  for (const r of rows) counts[r.tier] += 1
  const remote = rows.filter((r) => r.remote).length

  const items: { label: string; value: number; color?: string }[] = [
    { label: 'Total', value: rows.length },
    { label: 'Remote', value: remote },
    ...TIERS.map((t) => ({ label: t, value: counts[t], color: TIER_COLOR[t] })),
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {items.map((it) => (
        <div
          key={it.label}
          className="js-gradient-card js-kpi-card rounded-[16px] border border-border bg-card px-4 py-4"
          style={{ '--kpi-color': it.color ?? 'var(--accent)' } as CSSProperties}
        >
          <div className="text-3xl font-black leading-none tnum" style={it.color ? { color: it.color } : undefined}>
            <CountUp value={it.value} />
          </div>
          <div className="mt-1.5 text-[11px] font-bold uppercase tracking-[0.18em] text-mute">{it.label}</div>
        </div>
      ))}
    </div>
  )
}
