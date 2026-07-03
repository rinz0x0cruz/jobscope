import { useEffect, useState } from 'react'
import type { BarItem } from '@/lib/overview'

/** Horizontal bars whose widths grow in via a CSS transition (time-based). */
export function Bars({ items, color = 'var(--accent)' }: { items: BarItem[]; color?: string }) {
  const [on, setOn] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setOn(true), 40)
    return () => clearTimeout(id)
  }, [])

  if (items.length === 0) return null
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <div className="flex flex-col gap-2.5">
      {items.map((it, i) => (
        <div key={it.label}>
          <div className="mb-1 flex items-center justify-between gap-2 text-[13px]">
            <span className="min-w-0 truncate text-fg">{it.label}</span>
            <span className="shrink-0 text-mute tnum">{it.value}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full"
              style={{
                background: color,
                width: on ? `${(it.value / max) * 100}%` : '0%',
                transition: `width 0.6s ease-out ${i * 0.04}s`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
