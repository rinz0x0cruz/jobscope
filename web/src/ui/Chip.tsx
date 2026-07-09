import { X } from 'lucide-react'
import type { ReactNode } from 'react'

export interface ChipProps {
  children: ReactNode
  /** When provided, renders a trailing remove (×) button. */
  onRemove?: () => void
}

/**
 * Small rounded tag used for active filters / selected facets. Renders a compact
 * remove button (labelled "Remove") when `onRemove` is supplied.
 */
export function Chip({ children, onRemove }: ChipProps) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-inset px-2.5 py-0.5 text-[12px] text-ink-2">
      {children}
      {onRemove && (
        <button
          type="button"
          aria-label="Remove"
          onClick={onRemove}
          className="-mr-0.5 inline-flex items-center justify-center rounded-full text-ink-3 transition-colors hover:text-ink outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      )}
    </span>
  )
}
