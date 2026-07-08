import { motion } from 'motion/react'
import type { TabValue } from '@/lib/urlState'

// The fit-tier filter that lives inside "Jobs" (it used to be four top-level tabs).
// A radiogroup: exactly one tier is active and it writes the same `tab` URL param,
// so deep links like #/?tab=Strong still resolve.
const TIERS: { key: TabValue; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'Strong', label: 'Strong' },
  { key: 'Good', label: 'Good' },
  { key: 'Stretch', label: 'Stretch' },
  { key: 'Skip', label: 'Skip' },
]

export function TierSegment({
  value,
  counts,
  onChange,
}: {
  value: TabValue
  counts: Record<TabValue, number>
  onChange: (t: TabValue) => void
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Filter by fit tier"
      className="flex flex-wrap gap-1 self-start rounded-full border border-border bg-card p-1"
    >
      {TIERS.map((t) => {
        const active = t.key === value
        return (
          <button
            key={t.key}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(t.key)}
            className={
              'relative rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors ' +
              (active ? 'text-accent' : 'text-dim hover:text-fg')
            }
          >
            {active && (
              <motion.span
                layoutId="tier-indicator"
                className="absolute inset-0 rounded-full bg-accent-dim"
                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative z-10">
              {t.label}
              <span className="ml-1.5 text-mute tnum">{counts[t.key]}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
