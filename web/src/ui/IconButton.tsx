import type { ButtonHTMLAttributes } from 'react'

/** Control density of an {@link IconButton}. */
export type IconButtonSize = 'sm' | 'md'

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible name for the icon-only control (rendered as `aria-label`). */
  label: string
  size?: IconButtonSize
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

const BASE =
  'inline-flex items-center justify-center rounded-card text-ink-2 transition-colors ' +
  'hover:bg-inset hover:text-ink disabled:opacity-50 disabled:pointer-events-none ' +
  'outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1'

const SIZES: Record<IconButtonSize, string> = {
  sm: 'h-8 w-8',
  md: 'h-9 w-9',
}

/**
 * Square, icon-only button with secondary-ghost styling. The required `label`
 * becomes the `aria-label`; render a `lucide-react` icon as the child.
 */
export function IconButton({
  label,
  size = 'md',
  type,
  className,
  children,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      aria-label={label}
      className={cx(BASE, SIZES[size], className)}
      {...rest}
    >
      {children}
    </button>
  )
}
