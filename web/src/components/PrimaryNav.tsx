import { motion } from 'motion/react'
import type { TabValue } from '@/lib/urlState'

// The three primary destinations. The four tier buckets (all/Strong/Good/Stretch/
// Skip) collapse under "Jobs" and are chosen with the TierSegment, so the top nav
// stays about *where you are*, not *what you're filtering*.
export type Primary = 'overview' | 'jobs' | 'applications' | 'outreach'

const PRIMARIES: { key: Primary; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'jobs', label: 'Jobs' },
  { key: 'applications', label: 'Applications' },
  { key: 'outreach', label: 'Outreach' },
]

/** Which primary a `tab` param belongs to (any tier bucket ⇒ Jobs). */
export function primaryFor(tab: TabValue): Primary {
  if (tab === 'overview') return 'overview'
  if (tab === 'applications') return 'applications'
  if (tab === 'outreach') return 'outreach'
  return 'jobs'
}

export function PrimaryNav({
  tab,
  jobsCount,
  appsCount,
  onSelect,
}: {
  tab: TabValue
  jobsCount: number
  appsCount: number
  onSelect: (p: Primary) => void
}) {
  const active = primaryFor(tab)
  const counts: Record<Primary, number | null> = {
    overview: null,
    jobs: jobsCount,
    applications: appsCount,
    outreach: null,
  }
  return (
    <div
      role="tablist"
      aria-label="Primary sections"
      className="flex gap-1 self-start rounded-full border border-border bg-card p-1"
    >
      {PRIMARIES.map((p) => {
        const isActive = p.key === active
        return (
          <button
            key={p.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onSelect(p.key)}
            className={
              'relative rounded-full px-4 py-1.5 text-[13px] font-medium transition-colors ' +
              (isActive ? 'text-accent' : 'text-dim hover:text-fg')
            }
          >
            {isActive && (
              <motion.span
                layoutId="primary-indicator"
                className="absolute inset-0 rounded-full bg-accent-dim"
                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
              />
            )}
            <span className="relative z-10">
              {p.label}
              {counts[p.key] !== null && (
                <span className="ml-1.5 text-mute tnum">{counts[p.key]}</span>
              )}
            </span>
          </button>
        )
      })}
    </div>
  )
}
