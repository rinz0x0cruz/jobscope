import type { Application, JobRow } from '@/lib/schema'
import { GRADE_COLOR, chances, velocity } from '@/lib/gamification'

function Gauge({ score, color, grade }: { score: number; color: string; grade: string }) {
  const r = 26
  const circ = 2 * Math.PI * r
  const dash = (Math.max(0, Math.min(100, score)) / 100) * circ
  return (
    <div className="relative grid h-[70px] w-[70px] shrink-0 place-items-center">
      <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" stroke="var(--border)" strokeWidth="6" />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
        />
      </svg>
      <div className="absolute flex flex-col items-center leading-none">
        <span className="text-lg font-bold tnum" style={{ color }}>{score}</span>
        <span className="text-[10px] font-semibold text-mute">{grade}</span>
      </div>
    </div>
  )
}

/** "Momentum" overview card (issue #35): a single Chances score plus application
 *  velocity/streak stats and the factor breakdown. All derived client-side. */
export function Momentum({ rows, apps }: { rows: JobRow[]; apps: Application[] }) {
  const v = velocity(rows, apps)
  const c = chances(apps, rows)
  const color = GRADE_COLOR[c.grade]

  const stats: { label: string; value: string | number }[] = [
    { label: 'Applied · 7d', value: v.applied7 },
    { label: 'Streak', value: `${v.streakWeeks} wk${v.streakWeeks === 1 ? '' : 's'}` },
    { label: 'Avg / week', value: v.perWeek },
    { label: 'New · 7d', value: v.surfaced7 },
  ]
  const factors: { label: string; value: number }[] = [
    { label: 'Matches', value: c.factors.matches },
    { label: 'Pipeline', value: c.factors.pipeline },
    { label: 'Momentum', value: c.factors.momentum },
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center gap-3">
        <Gauge score={c.score} color={color} grade={c.grade} />
        <div className="min-w-0">
          <div className="text-sm font-semibold" style={{ color }}>{c.label}</div>
          <div className="text-[11.5px] leading-snug text-mute">
            Chances — a blend of match quality, pipeline conversion, and recent momentum.
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-[10px] border border-border bg-bg2/70 p-2">
            <div className="text-[10px] uppercase tracking-wide text-mute">{s.label}</div>
            <div className="text-base font-semibold tnum">{s.value}</div>
          </div>
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-1.5">
        {factors.map((f) => (
          <div key={f.label} className="flex items-center gap-2">
            <span className="w-16 shrink-0 text-[11px] text-mute">{f.label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border">
              <div className="h-full rounded-full" style={{ width: `${f.value}%`, background: color }} />
            </div>
            <span className="w-7 shrink-0 text-right text-[11px] tnum text-dim">{f.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
