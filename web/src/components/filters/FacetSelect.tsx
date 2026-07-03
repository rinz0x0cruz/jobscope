import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, ChevronDown } from 'lucide-react'
import type { FacetOption } from '@/lib/filters'

export function FacetSelect({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string
  options: FacetOption[]
  selected: string[]
  onToggle: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const n = selected.length
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={
          'flex items-center gap-1.5 rounded-[10px] border px-3 py-1.5 text-[13px] transition ' +
          (n > 0
            ? 'border-accent bg-accent-dim text-accent'
            : 'border-border bg-card text-dim hover:border-border-h hover:text-fg')
        }
      >
        {label}
        {n > 0 && <span className="rounded-full bg-accent/20 px-1.5 text-[11px] tnum">{n}</span>}
        <ChevronDown size={14} className={'transition ' + (open ? 'rotate-180' : '')} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.14 }}
            className="absolute left-0 z-30 mt-1.5 max-h-72 w-60 overflow-auto rounded-[12px] border border-border bg-card p-1 shadow-[var(--shadow)]"
          >
            {options.length === 0 && <div className="px-3 py-2 text-xs text-mute">No options</div>}
            {options.map((o) => {
              const on = selected.includes(o.value)
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => onToggle(o.value)}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition hover:bg-card-h"
                >
                  <span
                    className={
                      'grid h-4 w-4 shrink-0 place-items-center rounded border ' +
                      (on ? 'border-accent bg-accent text-white' : 'border-border')
                    }
                  >
                    {on && <Check size={11} />}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-fg">{o.value}</span>
                  <span className="text-mute tnum">{o.count}</span>
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
