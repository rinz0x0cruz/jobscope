import type { ButtonHTMLAttributes } from 'react'

/** Visual weight of a {@link Button}. */
export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
/** Control density of a {@link Button}. */
export type ButtonSize = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

const BASE =
  'inline-flex items-center gap-1.5 rounded-card font-medium transition-colors ' +
  'disabled:opacity-50 disabled:pointer-events-none ' +
  'outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1'

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-brand text-white hover:bg-brand-strong',
  secondary: 'bg-panel border border-line text-ink hover:bg-inset',
  ghost: 'text-ink-2 hover:bg-inset',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-[13px]',
  md: 'px-3.5 py-2 text-sm',
}

/**
 * Flat, token-driven button. Defaults to `type="button"` so it never submits a
 * form by accident; pass `type` to override. Forwards `className` (merged after
 * the variant/size classes) and spreads all other native button props.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  type,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      className={cx(BASE, VARIANTS[variant], SIZES[size], className)}
      {...rest}
    />
  )
}
