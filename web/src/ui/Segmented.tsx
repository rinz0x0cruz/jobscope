import type { ReactNode } from 'react'

export interface SegmentedOption {
  value: string
  label: ReactNode
  count?: number
}

export interface SegmentedProps {
  options: SegmentedOption[]
  value: string
  onChange: (value: string) => void
  /** Accessible name for the radiogroup. */
  ariaLabel: string
  className?: string
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * Single-select segmented control implemented as an ARIA `radiogroup`. The
 * active segment reads as a raised panel chip; the rest are quiet text buttons.
 */
export function Segmented({ options, value, onChange, ariaLabel, className }: SegmentedProps) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cx('inline-flex gap-1 rounded-card bg-inset p-1', className)}
    >
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cx(
              'inline-flex items-center gap-1.5 rounded-card px-3 py-1.5 text-[13px] font-medium transition-colors',
              'outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1',
              active ? 'bg-panel text-ink shadow-[var(--shadow-panel)]' : 'text-ink-2 hover:text-ink',
            )}
          >
            <span>{option.label}</span>
            {option.count != null && (
              <span className="tabular-nums text-ink-3">{option.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}
