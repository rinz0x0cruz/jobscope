import { motion } from 'motion/react'
import type { TabValue } from '@/lib/urlState'
import { TAB_VALUES } from '@/lib/urlState'

const LABELS: Record<TabValue, string> = {
  overview: 'Overview',
  applications: 'Applications',
  all: 'All',
  Strong: 'Strong',
  Good: 'Good',
  Stretch: 'Stretch',
  Skip: 'Skip',
}

export function Tabs({
  value,
  counts,
  onChange,
}: {
  value: TabValue
  counts: Record<TabValue, number>
  onChange: (t: TabValue) => void
}) {
  return (
    <div className="flex flex-wrap gap-1 self-start rounded-full border border-border bg-card p-1">
      {TAB_VALUES.map((t) => {
        const active = t === value
        return (
          <button
            key={t}
            type="button"
            onClick={() => onChange(t)}
            className={
              'relative rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors ' +
              (active ? 'text-accent' : 'text-dim hover:text-fg')
            }
          >
            {active && (
              <motion.span
                layoutId="tab-indicator"
                className="absolute inset-0 rounded-full bg-accent-dim"
                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative z-10">
              {LABELS[t]}
              {t !== 'overview' && <span className="ml-1.5 text-mute tnum">{counts[t]}</span>}
            </span>
          </button>
        )
      })}
    </div>
  )
}
