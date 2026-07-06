import { useEffect, useState } from 'react'
import type { Seg } from '@/lib/overview'

const R = 50
const C = 2 * Math.PI * R

/** SVG donut. Arcs render to their final geometry and grow in via a CSS
 *  stroke-dasharray transition (time-based, so it's reliable everywhere). */
export function Donut({ segs, total }: { segs: Seg[]; total: number }) {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setOn(true), 40)
    return () => clearTimeout(id)
  }, [])

  return (
    <div className="flex h-full min-h-[132px] flex-col items-center justify-center gap-3">
      <div className="relative mx-auto aspect-square w-full max-w-[260px]">
        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
          <circle cx={60} cy={60} r={R} fill="none" stroke="var(--border)" strokeWidth={14} />
          {segs.map((s) => (
            <circle
              key={s.label}
              cx={60}
              cy={60}
              r={R}
              fill="none"
              stroke={s.color}
              strokeWidth={14}
              strokeLinecap="butt"
              strokeDasharray={on ? `${s.fraction * C} ${C}` : `0 ${C}`}
              strokeDashoffset={-s.start * C}
              style={{ transition: 'stroke-dasharray 0.8s ease-out' }}
            />
          ))}
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <div className="text-center">
            <div className="text-3xl font-semibold tnum">{total}</div>
            <div className="text-xs text-mute">roles</div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center gap-2 text-[13px]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-fg">{s.label}</span>
            <span className="text-mute tnum">{s.value}</span>
            <span className="text-mute">({Math.round((s.value / (total || 1)) * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  )
}
