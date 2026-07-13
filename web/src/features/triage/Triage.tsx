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
  const groups: { tier: Tier; items: TriageItem[] }[] = []
  for (const it of shown) {
    const last = groups[groups.length - 1]
    if (last && last.tier === it.tier) last.items.push(it)
    else groups.push({ tier: it.tier, items: [it] })
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex items-center justify-between gap-3">
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

      <div className="space-y-7">
        {groups.map((group) => (
          <section key={group.tier}>
            <div
              className="mb-2.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider"
              style={{ color: TIER_COLOR[group.tier] }}
            >
              <span>{group.tier}</span>
              <span className="text-ink-3">{items.filter((i) => i.tier === group.tier).length}</span>
            </div>
            <ul className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
              {group.items.map((item) => (
                <li key={item.jobId}>
                  <TriageRow item={item} onOpen={onOpen} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

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
    <div className="group relative flex h-full flex-col overflow-hidden rounded-card border border-line bg-panel transition-colors hover:border-line-strong">
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1"
        style={{ background: TIER_COLOR[item.tier] }}
      />
      <button
        type="button"
        onClick={() => onOpen(item.jobId)}
        aria-label={`${item.company} — ${item.title}`}
        className="flex min-w-0 flex-1 flex-col gap-2 py-3 pl-4 pr-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
      >
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-semibold leading-snug text-ink">
              {item.title || item.company}
            </span>
            {item.title && (
              <span className="mt-0.5 block truncate text-[12px] text-ink-2">{item.company}</span>
            )}
          </span>
          <span
            className="mt-0.5 shrink-0 text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: TIER_COLOR[item.tier] }}
          >
            {item.tier}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
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
            {item.coveragePct != null && (
              <span title="How much of the JD's requirements your résumé covers (deterministic)">
                · covers {Math.round(item.coveragePct)}%
              </span>
            )}
          </span>
      </button>

      {item.url && (
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-3 ml-4 inline-flex w-fit items-center gap-1 rounded-card border border-line px-2.5 py-1.5 text-[12px] font-medium text-brand outline-none transition-colors hover:border-brand hover:bg-brand-weak focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ExternalLink size={13} aria-hidden="true" />
          Apply
        </a>
      )}
    </div>
  )
}
