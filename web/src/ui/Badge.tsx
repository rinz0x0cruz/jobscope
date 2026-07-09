import type { ReactNode } from 'react'

/** Semantic color of a {@link Badge}. */
export type BadgeTone = 'neutral' | 'brand' | 'strong' | 'good' | 'stretch' | 'skip'

export interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-inset text-ink-2',
  brand: 'bg-brand-weak text-brand',
  strong: 'bg-inset text-strong',
  good: 'bg-inset text-good',
  stretch: 'bg-inset text-stretch',
  skip: 'bg-inset text-skip',
}

/**
 * Tiny uppercase status pill. `neutral`/`brand` carry their own fill; the tier
 * tones (`strong`/`good`/`stretch`/`skip`) tint the label over a faint inset.
 */
export function Badge({ tone = 'neutral', children }: BadgeProps) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
        TONES[tone],
      )}
    >
      {children}
    </span>
  )
}
