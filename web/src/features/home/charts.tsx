// Lightweight, dependency-free SVG/CSS charts for the Home dashboard. Token-driven
// (theme CSS vars) so they follow light/dark automatically. Presentational only.

import type { BarItem, DonutSeg, FunnelStage, TrendPoint } from '@/lib/overview'

function Empty({ label }: { label: string }) {
  return <div className="flex h-24 items-center justify-center text-sm text-ink-3">{label}</div>
}

/** Ring chart for the fit-tier split: a compact, gapped donut with the total in
 *  the middle and a tidy legend beneath. */
export function Donut({ segs, total }: { segs: DonutSeg[]; total: number }) {
  if (total <= 0 || segs.length === 0) return <Empty label="No roles yet" />
  const size = 148
  const stroke = 14
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const mid = size / 2
  const gap = segs.length > 1 ? 0.014 : 0
  return (
    <div className="flex flex-col items-center gap-5">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="shrink-0"
        role="img"
        aria-label="Fit distribution"
      >
        <g transform={`rotate(-90 ${mid} ${mid})`}>
          <circle cx={mid} cy={mid} r={r} fill="none" stroke="var(--inset)" strokeWidth={stroke} />
          {segs.map((s) => {
            const len = Math.max((s.fraction - gap) * c, 0.5)
            return (
              <circle
                key={s.label}
                cx={mid}
                cy={mid}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={stroke}
                strokeLinecap="round"
                strokeDasharray={`${len} ${c - len}`}
                strokeDashoffset={-(s.start + gap / 2) * c}
              />
            )
          })}
        </g>
        <text
          x="50%"
          y="45%"
          textAnchor="middle"
          dominantBaseline="middle"
          className="font-mono text-[26px] font-semibold"
          style={{ fill: 'var(--ink)' }}
        >
          {total}
        </text>
        <text
          x="50%"
          y="60%"
          textAnchor="middle"
          dominantBaseline="middle"
          className="text-[10px] font-semibold uppercase"
          style={{ fill: 'var(--ink-3)', letterSpacing: '0.1em' }}
        >
          roles
        </text>
      </svg>
      <ul className="w-full space-y-2">
        {segs.map((s) => (
          <li key={s.label} className="flex items-center gap-2 text-sm">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: s.color }}
              aria-hidden="true"
            />
            <span className="text-ink-2">{s.label}</span>
            <span className="ml-auto font-mono tabular-nums text-ink">{s.value}</span>
            <span className="w-10 text-right font-mono text-ink-3">
              {Math.round(s.fraction * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Horizontal bar list (top companies / locations / sources). */
export function BarRows({
  items,
  color = 'var(--brand-coral)',
  emptyLabel = 'No data yet',
}: {
  items: BarItem[]
  color?: string
  emptyLabel?: string
}) {
  if (items.length === 0) return <Empty label={emptyLabel} />
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <ul className="space-y-2">
      {items.map((it) => (
        <li key={it.label} className="grid grid-cols-[5rem_1fr_1.75rem] items-center gap-2.5 text-sm">
          <span className="truncate text-ink-2" title={it.label}>
            {it.label}
          </span>
          <span className="h-2.5 overflow-hidden rounded-full bg-inset">
            <span
              className="block h-full rounded-full"
              style={{ width: `${(it.value / max) * 100}%`, background: it.color ?? color }}
            />
          </span>
          <span className="text-right font-mono tabular-nums text-ink">{it.value}</span>
        </li>
      ))}
    </ul>
  )
}

/** Conversion funnel: descending bars with per-step conversion %. */
export function Funnel({ stages }: { stages: FunnelStage[] }) {
  return (
    <ul className="space-y-3">
      {stages.map((s, i) => {
        const prev = i > 0 ? stages[i - 1].value : null
        const conv = prev && prev > 0 ? Math.round((s.value / prev) * 100) : null
        return (
          <li key={s.key} className="text-sm">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-ink-2">{s.label}</span>
              <span className="font-mono tabular-nums text-ink">
                {s.value}
                {conv !== null && <span className="ml-2 text-ink-3">{conv}%</span>}
              </span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-inset">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${s.value > 0 ? Math.max(s.fraction * 100, 3) : 0}%`,
                  background: s.color,
                }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** Filled area + line for roles surfaced per week, with faint gridlines. */
export function TrendArea({
  points,
  color = 'var(--chart-indigo)',
}: {
  points: TrendPoint[]
  color?: string
}) {
  const w = 100
  const h = 44
  const n = points.length
  const max = Math.max(1, ...points.map((p) => p.value))
  const x = (i: number) => (n <= 1 ? w / 2 : (i / (n - 1)) * w)
  const y = (v: number) => h - 3 - (v / max) * (h - 6)
  const line = points.map((p, i) => `${x(i).toFixed(2)},${y(p.value).toFixed(2)}`).join(' ')
  const area = `0,${h} ${line} ${w},${h}`
  const gridYs = [0.5, 1].map((f) => y(max * f))
  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="h-32 w-full"
        role="img"
        aria-label="Roles surfaced per week"
      >
        {gridYs.map((gy, i) => (
          <line
            key={i}
            x1={0}
            y1={gy}
            x2={w}
            y2={gy}
            stroke="var(--line)"
            strokeWidth={1}
            strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <polygon points={area} fill={color} opacity={0.14} />
        <polyline
          points={line}
          fill="none"
          stroke={color}
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      <div className="mt-1.5 flex justify-between text-[10px] tabular-nums text-ink-3">
        {points.map((p, i) => (
          <span key={`${p.label}-${i}`}>{p.label}</span>
        ))}
      </div>
    </div>
  )
}

/** Vertical bars for the score histogram: width-capped, centered, on a baseline. */
export function VBars({ items }: { items: BarItem[] }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <div>
      <div className="flex h-40 items-end gap-2 border-b border-line" role="img" aria-label="Score distribution">
        {items.map((it) => (
          <div key={it.label} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1.5">
            <span className="font-mono text-[11px] tabular-nums text-ink-3">{it.value}</span>
            <div
              className="w-full max-w-[2.5rem] rounded-t-md transition-all"
              style={{
                height: `${(it.value / max) * 100}%`,
                minHeight: it.value > 0 ? 4 : 0,
                background: it.color ?? 'var(--brand-coral)',
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-2">
        {items.map((it) => (
          <span key={it.label} className="flex-1 text-center text-[11px] text-ink-2">
            {it.label}
          </span>
        ))}
      </div>
    </div>
  )
}
