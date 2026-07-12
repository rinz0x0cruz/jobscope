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
  const [hideStale, setHideStale] = useState(false)
  const [hideNoSalary, setHideNoSalary] = useState(false)
  const filtered = useMemo(() => filterTriage(queue, query), [queue, query])
  const staleCount = useMemo(() => filtered.items.filter((i) => i.stale).length, [filtered])
  const noSalaryCount = useMemo(
    () => filtered.items.filter((i) => !i.salary.trim()).length,
    [filtered],
  )
  const items = filtered.items.filter(
    (i) => (!hideStale || !i.stale) && (!hideNoSalary || i.salary.trim() !== ''),
  )

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
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-ink-3">
          {items.length} role{items.length === 1 ? '' : 's'} to apply to, best fit first.
        </p>
        <div className="flex shrink-0 items-center gap-2">
          {staleCount > 0 && (
            <FilterToggle
              active={hideStale}
              onClick={() => setHideStale((v) => !v)}
              label={hideStale ? 'Showing fresh only' : `Hide stale (${staleCount})`}
            />
          )}
          {noSalaryCount > 0 && (
            <FilterToggle
              active={hideNoSalary}
              onClick={() => setHideNoSalary((v) => !v)}
              label={hideNoSalary ? 'With salary only' : `Hide no-salary (${noSalaryCount})`}
            />
          )}
        </div>
      </div>

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

function FilterToggle({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        'shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
        active ? 'border-brand bg-brand-weak text-brand' : 'border-line text-ink-3 hover:border-line-strong',
      )}
    >
      {label}
    </button>
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
            {item.stale && (
              <span
                className="inline-flex items-center rounded-full bg-inset px-1.5 py-0.5 text-[10px] font-medium text-ink-3"
                title={
                  item.postedAgeDays != null
                    ? `Posted ${item.postedAgeDays}d ago \u2014 likely stale/ghost`
                    : 'Likely stale/ghost'
                }
              >
                stale
              </span>
            )}
            {item.remoteMismatch && (
              <span
                className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                style={{ color: 'var(--hot)', background: 'color-mix(in srgb, var(--hot) 14%, transparent)' }}
                title="Tagged remote, but the description mentions onsite/hybrid"
              >
                remote?
              </span>
            )}
            {item.sources.length > 1 && (
              <span title={`Also posted on ${item.sources.slice(1).join(', ')}`}>
                · also on {item.sources.slice(1).join(', ')}
              </span>
            )}
            {item.hasReferral && (
              <span
                className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                style={{ color: 'var(--strong)', background: 'color-mix(in srgb, var(--strong) 14%, transparent)' }}
                title="A referral path exists for this company"
              >
                referral
              </span>
            )}
            {!item.salary.trim() && <span>· no salary</span>}
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
