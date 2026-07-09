// The "Triage" lens — a keyboard-first review queue that shows ONE role at a
// time (an inbox you clear), so you can quickly decide what to pursue. Purely
// presentational + session-local: it walks an already-derived `TriageQueue`
// (see `@/lib/triage`) one card at a time, tracking a cursor and a dismissed
// set in local state, and reports role opens upward. No data fetching, no
// persistence — skips live only for this session.

import type { KeyboardEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, CheckCircle2, ExternalLink, MapPin, X } from 'lucide-react'
import { Button } from '@/ui'
import type { TriageItem, TriageQueue } from '@/lib/triage'

export interface TriageProps {
  queue: TriageQueue
  onOpen: (jobId: string) => void
}

/** Tier → accent color for the corner micro-label (matches the legend hues). */
const TIER_COLOR: Record<TriageItem['tier'], string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}

/** "surfaced …" phrasing for the meta line; 0 days reads as "today". */
function surfaced(ageDays: number): string {
  return ageDays === 0 ? 'surfaced today' : `surfaced ${ageDays}d ago`
}

/**
 * The Triage lens: a centered, single-card review queue. Skip clears the
 * current role (advancing to the next as the list shrinks), Prev steps back,
 * Details opens the drawer, and Apply opens the posting. Keyboard-first:
 * →/x skip · ← prev · o/Enter open · a apply.
 */
export function Triage({ queue, onOpen }: TriageProps) {
  const [index, setIndex] = useState(0)
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set())
  const rootRef = useRef<HTMLDivElement>(null)

  // Focus the queue on mount so the keyboard shortcuts work without a click.
  useEffect(() => {
    rootRef.current?.focus()
  }, [])

  const visible = queue.items.filter((item) => !dismissed.has(item.jobId))
  const visibleCount = visible.length
  const clamped = Math.min(index, Math.max(0, visibleCount - 1))
  const current = visible[clamped]

  const cleared = Math.max(0, queue.total - visibleCount)
  const pct = queue.total > 0 ? Math.min(100, (cleared / queue.total) * 100) : 0

  function skip() {
    if (!current) return
    const id = current.jobId
    setDismissed((prev) => {
      const next = new Set(prev)
      next.add(id)
      return next
    })
  }

  function prev() {
    setIndex(Math.max(0, clamped - 1))
  }

  function openDetails() {
    if (current) onOpen(current.jobId)
  }

  function apply() {
    if (current?.url) window.open(current.url, '_blank', 'noopener,noreferrer')
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
    if (!current) return
    switch (e.key) {
      case 'ArrowRight':
      case 'x':
        e.preventDefault()
        skip()
        break
      case 'ArrowLeft':
        e.preventDefault()
        prev()
        break
      case 'o':
      case 'Enter':
        e.preventDefault()
        openDetails()
        break
      case 'a':
        e.preventDefault()
        apply()
        break
      default:
        break
    }
  }

  return (
    <div
      ref={rootRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      className="mx-auto max-w-xl outline-none"
    >
      {current ? (
        <>
          <div className="mb-4">
            <div className="flex items-baseline justify-between">
              <span className="font-display text-sm font-semibold text-ink">Reviewing</span>
              <span className="text-[12px] text-ink-3">{visibleCount} left</span>
            </div>
            <div
              className="mt-2 h-1 w-full overflow-hidden rounded-full bg-inset"
              role="progressbar"
              aria-valuenow={cleared}
              aria-valuemin={0}
              aria-valuemax={queue.total}
            >
              <div
                className="h-full rounded-full bg-brand transition-[width]"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          <div className="rounded-card border border-line bg-panel p-6 shadow-[var(--shadow-panel)]">
            <div className="flex items-start justify-between gap-3">
              <span className="text-lg font-semibold text-ink">{current.company}</span>
              <span className="flex shrink-0 items-center gap-2">
                <span
                  className="text-[11px] font-semibold uppercase"
                  style={{ color: TIER_COLOR[current.tier] }}
                >
                  {current.tier}
                </span>
                <span className="text-sm text-ink-3">{current.score}</span>
              </span>
            </div>

            <p className="mt-1 text-[15px] text-ink-2">{current.title}</p>

            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-3">
              {current.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                  {current.location}
                </span>
              )}
              {current.remote && current.location.toLowerCase() !== 'remote' && <span>Remote</span>}
              {current.ageDays != null && <span>{surfaced(current.ageDays)}</span>}
            </div>

            {current.brief && (
              <p className="mt-4 text-[14px] leading-relaxed text-ink-2">{current.brief}</p>
            )}

            <div className="mt-6 flex items-center gap-2">
              {clamped > 0 && (
                <Button variant="ghost" size="sm" onClick={prev} aria-label="Prev">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={skip}>
                <X className="h-4 w-4" aria-hidden="true" />
                Skip
              </Button>
              <Button variant="secondary" size="sm" onClick={openDetails}>
                Details
              </Button>
              <Button variant="primary" size="sm" onClick={apply} className="ml-auto">
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
                Apply
              </Button>
            </div>

            <p className="mt-3 text-[11px] text-ink-3">← prev · → skip · O open · A apply</p>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-card border border-line bg-panel px-6 py-16 text-center shadow-[var(--shadow-panel)]">
          <CheckCircle2 className="h-10 w-10 text-brand" aria-hidden="true" />
          <p className="mt-4 font-display text-lg font-semibold text-ink">All caught up</p>
          <p className="mt-1 text-sm text-ink-3">
            Nothing left to review — new roles will show up here.
          </p>
        </div>
      )}
    </div>
  )
}
