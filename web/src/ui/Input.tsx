import { forwardRef } from 'react'
import type { InputHTMLAttributes } from 'react'

export type InputProps = InputHTMLAttributes<HTMLInputElement>

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

const BASE =
  'w-full rounded-card border border-line bg-panel px-3 py-2 text-sm text-ink ' +
  'placeholder:text-ink-3 outline-none focus-visible:ring-2 focus-visible:ring-brand'

/**
 * Flat text input on the panel surface. Forwards its ref to the underlying
 * `<input>` and merges any `className` after the base styles.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { type, className, ...rest },
  ref,
) {
  return <input ref={ref} type={type ?? 'text'} className={cx(BASE, className)} {...rest} />
})
