import type { ReactNode } from 'react'

export interface CardProps {
  /** Optional header title; when present a header row is rendered. */
  title?: ReactNode
  /** Optional right-aligned header actions (buttons, menus, …). */
  actions?: ReactNode
  children?: ReactNode
  className?: string
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * Flat surface panel: hairline border, `rounded-card`, subtle panel shadow, and
 * generous padding. Renders an optional header row (`title` + `actions`).
 */
export function Card({ title, actions, children, className }: CardProps) {
  const hasHeader = title != null || actions != null
  return (
    <div
      className={cx(
        'rounded-card border border-line bg-panel shadow-[var(--shadow-panel)] p-5',
        className,
      )}
    >
      {hasHeader && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title != null && (
            <div className="text-sm font-semibold text-ink">{title}</div>
          )}
          {actions != null && (
            <div className="flex items-center gap-2">{actions}</div>
          )}
        </div>
      )}
      {children}
    </div>
  )
}
