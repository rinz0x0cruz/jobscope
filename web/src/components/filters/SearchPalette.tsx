import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { AnimatePresence, motion } from 'motion/react'
import { Search } from 'lucide-react'
import type { JobRow } from '@/lib/schema'
import { TIER_COLOR } from '@/lib/schema'
import { fuzzy, makeFuse } from '@/lib/search'

function isTyping(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
}

/** Ctrl/Cmd-K (or "/") command palette: fuzzy-search every role, Enter opens Apply. */
export function SearchPalette({ rows }: { rows: JobRow[] }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const fuse = useMemo(() => makeFuse(rows), [rows])
  const results = useMemo(
    () => (q.trim() ? fuzzy(fuse, rows, q) : rows).slice(0, 24),
    [fuse, rows, q],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !isTyping(e))) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const openJob = (row: JobRow) => {
    window.open(row.url, '_blank', 'noreferrer')
    setOpen(false)
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className="w-full max-w-xl overflow-hidden rounded-[16px] border border-border bg-card shadow-[var(--shadow)]"
          >
            <Command shouldFilter={false} className="flex flex-col" loop>
              <div className="flex items-center gap-2 border-b border-border px-4">
                <Search size={16} className="opacity-50" />
                <Command.Input
                  autoFocus
                  value={q}
                  onValueChange={setQ}
                  placeholder="Search all roles…"
                  className="flex-1 bg-transparent py-3.5 text-sm text-fg outline-none placeholder:text-mute"
                />
                <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] text-mute">esc</kbd>
              </div>
              <Command.List className="max-h-80 overflow-auto p-1.5">
                <Command.Empty className="px-3 py-6 text-center text-sm text-mute">
                  No roles found.
                </Command.Empty>
                {results.map((row) => (
                  <Command.Item
                    key={row.id}
                    value={row.id}
                    onSelect={() => openJob(row)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm transition data-[selected=true]:bg-card-h"
                  >
                    <span
                      className="tnum text-[13px] font-semibold"
                      style={{ color: TIER_COLOR[row.tier] }}
                    >
                      {Math.round(row.score)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-fg">{row.title}</span>
                    <span className="shrink-0 truncate text-xs text-mute">{row.company}</span>
                  </Command.Item>
                ))}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
