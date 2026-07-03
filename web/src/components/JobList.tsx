import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { motion } from 'motion/react'
import { ChevronDown } from 'lucide-react'
import type { DisplayItem } from '@/lib/filters'
import { JobCard } from './JobCard'

/** Virtualized list of display items (company headers + job cards) so 500+ rows
 *  stay at 60fps. Headers toggle group collapse. */
export function JobList({
  items,
  collapsed,
  onToggleCollapse,
}: {
  items: DisplayItem[]
  collapsed: ReadonlySet<string>
  onToggleCollapse: (company: string) => void
}) {
  const parentRef = useRef<HTMLDivElement>(null)

  const virt = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: (i) => (items[i].type === 'header' ? 40 : 132),
    overscan: 8,
    gap: 10,
  })

  if (items.length === 0) {
    return (
      <div className="grid place-items-center rounded-[14px] border border-dashed border-border py-16 text-sm text-mute">
        No roles match your filters.
      </div>
    )
  }

  return (
    <div ref={parentRef} className="max-h-[calc(100vh-320px)] overflow-auto pr-1">
      <div style={{ height: virt.getTotalSize(), position: 'relative', width: '100%' }}>
        {virt.getVirtualItems().map((v) => {
          const item = items[v.index]
          return (
            <div
              key={item.type === 'job' ? item.row.id : 'h:' + item.company}
              data-index={v.index}
              ref={virt.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${v.start}px)`,
              }}
            >
              {item.type === 'header' ? (
                <button
                  type="button"
                  onClick={() => onToggleCollapse(item.company)}
                  className="flex w-full items-center gap-2 py-1.5 text-left text-[13px] font-semibold"
                >
                  <ChevronDown
                    size={15}
                    className={'text-mute transition ' + (collapsed.has(item.company) ? '-rotate-90' : '')}
                  />
                  <span className="text-fg">{item.company}</span>
                  <span className="rounded-full bg-accent-dim px-1.5 text-[11px] text-accent tnum">
                    ×{item.count}
                  </span>
                </button>
              ) : (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18 }}
                >
                  <JobCard row={item.row} />
                </motion.div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
