import type { ReactNode } from 'react'

export interface StatCardDelta {
  value: string
  positive?: boolean
}

export interface StatCardProps {
  label: string
  value: ReactNode
  /** Optional leading icon, shown in a `bg-brand-weak` rounded square. */
  icon?: ReactNode
  /** Optional trend indicator, tinted `text-strong` when `positive`. */
  delta?: StatCardDelta
  className?: string
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * KPI tile built on the flat Card surface: a large mono value, an uppercase
 * micro-label, an optional brand-tinted icon, and an optional delta.
 */
export function StatCard({ label, value, icon, delta, className }: StatCardProps) {
  return (
    <div
      className={cx(
        'rounded-card border border-line bg-panel shadow-[var(--shadow-panel)] p-5',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-[11px] uppercase tracking-wide text-ink-3">{label}</span>
        {icon != null && (
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-card bg-brand-weak text-brand">
            {icon}
          </span>
        )}
      </div>
      <div className="mt-2 font-mono text-2xl font-semibold tabular-nums text-ink">
        {value}
      </div>
      {delta != null && (
        <div
          className={cx(
            'mt-1 text-xs font-medium',
            delta.positive ? 'text-strong' : 'text-ink-3',
          )}
        >
          {delta.value}
        </div>
      )}
    </div>
  )
}
