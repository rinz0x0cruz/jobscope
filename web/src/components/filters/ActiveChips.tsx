import { AnimatePresence, motion } from 'motion/react'
import { X } from 'lucide-react'
import type { ActiveChip } from '@/lib/filters'
import type { FacetKey } from '@/lib/urlState'
import { FACETS } from '@/lib/urlState'

const LABEL: Record<FacetKey, string> = Object.fromEntries(
  FACETS.map((f) => [f.key, f.label]),
) as Record<FacetKey, string>

export function ActiveChips({
  chips,
  onRemove,
}: {
  chips: ActiveChip[]
  onRemove: (key: FacetKey, value: string) => void
}) {
  if (chips.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      <AnimatePresence initial={false}>
        {chips.map((c) => (
          <motion.button
            key={c.key + ':' + c.value}
            type="button"
            layout
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
            onClick={() => onRemove(c.key, c.value)}
            className="flex items-center gap-1 rounded-full border border-accent bg-accent-dim px-2.5 py-1 text-[12px] text-accent"
          >
            <span className="text-mute">{LABEL[c.key]}:</span>
            {c.value}
            <X size={12} />
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  )
}
