import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { JobRow } from '@/lib/schema'
import { JobCard } from './JobCard'

/** Virtualized list — renders only the visible rows so 500+ cards stay at 60fps. */
export function JobList({ rows }: { rows: JobRow[] }) {
  const parentRef = useRef<HTMLDivElement>(null)

  const virt = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 132,
    overscan: 8,
    gap: 12,
  })

  if (rows.length === 0) {
    return (
      <div className="grid place-items-center rounded-[14px] border border-dashed border-border py-16 text-sm text-mute">
        No roles match your filters.
      </div>
    )
  }

  return (
    <div ref={parentRef} className="max-h-[calc(100vh-268px)] overflow-auto pr-1">
      <div style={{ height: virt.getTotalSize(), position: 'relative', width: '100%' }}>
        {virt.getVirtualItems().map((item) => (
          <div
            key={rows[item.index].id}
            data-index={item.index}
            ref={virt.measureElement}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${item.start}px)`,
            }}
          >
            <JobCard row={rows[item.index]} />
          </div>
        ))}
      </div>
    </div>
  )
}
