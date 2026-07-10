// The "To apply" lens: a ranked, tier-grouped list of roles you can still apply
// to. Best-fit first (the research pattern for relevance-ranked lists): tier
// dividers act as landmarks, and a "Show more" button reveals the rest on demand
// instead of an endless scroll. The topbar search filters it live.

import { useMemo, useState } from 'react'
import { ExternalLink, MapPin } from 'lucide-react'
import { Button } from '@/ui'
import { filterTriage } from '@/lib/triage'
import type { TriageItem, TriageQueue } from '@/lib/triage'
import type { Tier } from '@/lib/schema'

export interface TriageProps {
  queue: TriageQueue
  onOpen: (jobId: string) => void
  /** Live filter from the topbar search (empty = show everything). */
  query?: string
}

/** How many rows to show initially and reveal per "Show more". */
const PAGE = 15

const TIER_COLOR: Record<Tier, string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

export function Triage({ queue, onOpen, query = '' }: TriageProps) {
  const [visible, setVisible] = useState(PAGE)
  const filtered = useMemo(() => filterTriage(queue, query), [queue, query])
  const items = filtered.items

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-2xl py-20 text-center text-sm text-ink-3">
        {query ? 'No matches for that search.' : 'No new roles to apply to right now.'}
      </div>
    )
  }

  const shown = items.slice(0, visible)
  let lastTier: Tier | null = null

  return (
    <div className="mx-auto max-w-2xl">
      <p className="mb-4 text-sm text-ink-3">
        {items.length} role{items.length === 1 ? '' : 's'} to apply to, best fit first.
      </p>

      <ul className="space-y-1.5">
        {shown.map((item, idx) => {
          const header = item.tier !== lastTier ? item.tier : null
          lastTier = item.tier
          return (
            <li key={item.jobId}>
              {header && (
                <div
                  className={cx(
                    'mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider',
                    idx > 0 && 'mt-5',
                  )}
                  style={{ color: TIER_COLOR[header] }}
                >
                  <span>{header}</span>
                  <span className="text-ink-3">{items.filter((i) => i.tier === header).length}</span>
                </div>
              )}
              <TriageRow item={item} onOpen={onOpen} />
            </li>
          )
        })}
      </ul>

      {visible < items.length && (
        <div className="mt-5 flex justify-center">
          <Button variant="secondary" onClick={() => setVisible((v) => v + PAGE)}>
            Show {Math.min(PAGE, items.length - visible)} more
          </Button>
        </div>
      )}
    </div>
  )
}

function TriageRow({ item, onOpen }: { item: TriageItem; onOpen: (jobId: string) => void }) {
  return (
    <div className="group flex items-stretch gap-3 rounded-card border border-line bg-panel pr-2 transition-colors hover:border-line-strong">
      <button
        type="button"
        onClick={() => onOpen(item.jobId)}
        aria-label={`${item.company} — ${item.title}`}
        className="flex min-w-0 flex-1 items-stretch gap-3 py-2.5 pl-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span
          aria-hidden="true"
          className="w-1 shrink-0 rounded-full"
          style={{ background: TIER_COLOR[item.tier] }}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-[13px] font-semibold text-ink">{item.company}</span>
            <span
              className="shrink-0 text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: TIER_COLOR[item.tier] }}
            >
              {item.tier}
            </span>
          </span>
          <span className="mt-0.5 block truncate text-[12px] text-ink-2">{item.title}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-ink-3">
            {item.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={11} aria-hidden="true" />
                {item.location}
              </span>
            )}
            <span>· {item.score}</span>
            {item.ageDays != null && (
              <span>· {item.ageDays === 0 ? 'today' : `${item.ageDays}d ago`}</span>
            )}
          </span>
        </span>
      </button>

      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="my-2 inline-flex shrink-0 items-center gap-1 self-center rounded-card px-2.5 py-1.5 text-[12px] font-medium text-brand outline-none transition-colors hover:bg-brand-weak focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ExternalLink size={13} aria-hidden="true" />
          Apply
        </a>
      )}
    </div>
  )
}
