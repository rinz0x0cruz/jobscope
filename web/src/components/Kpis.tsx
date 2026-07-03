import type { JobRow, Tier } from '@/lib/schema'
import { TIERS, TIER_COLOR } from '@/lib/schema'

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
        <div key={it.label} className="rounded-[14px] border border-border bg-card px-4 py-3">
          <div className="text-2xl font-semibold tnum" style={it.color ? { color: it.color } : undefined}>
            {it.value}
          </div>
          <div className="mt-0.5 text-xs text-mute">{it.label}</div>
        </div>
      ))}
    </div>
  )
}
