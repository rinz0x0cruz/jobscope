import { useEffect, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowUpRight, BriefcaseBusiness, ChevronDown, Clock3, MapPin, Users } from 'lucide-react'
import type { FeedItem, FeedModel } from '@/lib/feed'
import { FACETS, FEED_FLAG_VALUES, type FeedFlag, type SearchState } from '@/lib/urlState'
import type { JobRow, Tier } from '@/lib/schema'
import { useScoreFormat } from '@/hooks/useScoreFormat'
import { scoreToGrade } from '@/lib/gamification'
import { presentFitRationale } from '@/lib/jobPresentation'

export interface FeedViewProps {
  model: FeedModel
  state: SearchState
  selectedId?: string
  onSelect: (jobId: string) => void
  onStateChange: (patch: Partial<SearchState>, options?: { replace?: boolean }) => void
}

const TIER_COLOR: Record<Tier, string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}

const FLAG_LABEL: Record<FeedFlag, string> = {
  remote: 'Remote',
  salary: 'Salary listed',
  referral: 'Referral',
  fresh: 'New this week',
  'hide-stale': 'Hide stale',
}

const PRIMARY_FLAGS: FeedFlag[] = ['remote', 'salary']
const SECONDARY_FLAGS = FEED_FLAG_VALUES.filter((flag) => !PRIMARY_FLAGS.includes(flag))

function toggle<T extends string>(items: T[], value: T): T[] {
  return items.includes(value) ? items.filter((item) => item !== value) : [...items, value]
}

function uniqueFacetValues(rows: JobRow[], get: (row: JobRow) => string): string[] {
  return [...new Set(rows.map(get).filter(Boolean))].sort((left, right) => left.localeCompare(right))
}

function FeedToolbar({ model, rows, state, onStateChange }: Pick<FeedViewProps, 'model' | 'state' | 'onStateChange'> & { rows: JobRow[] }) {
  const activeFilters = state.flags.length + state.tiers.length + FACETS.reduce((total, facet) => total + state[facet.key].length, 0)
  const advancedFilters =
    state.flags.filter((flag) => SECONDARY_FLAGS.includes(flag)).length +
    FACETS.reduce((total, facet) => total + state[facet.key].length, 0)
  return (
    <div className="border-b border-line bg-panel">
      <div className="flex min-h-12 items-center gap-3 border-b border-line px-4 py-2 sm:px-5">
        <div className="min-w-0 flex-1">
          <span className="font-medium text-ink">{model.total}</span>{' '}
          <span className="text-ink-3">of {model.available} available roles</span>
        </div>
        <label className="flex items-center gap-2 text-[12px] text-ink-3">
          <span className="hidden sm:inline">Sort</span>
          <select
            aria-label="Sort roles"
            value={state.sort}
            onChange={(event) => onStateChange({ sort: event.target.value as SearchState['sort'] })}
            className="h-8 rounded-md border border-line bg-paper px-2 text-[12px] text-ink outline-none focus:border-line-strong"
          >
            <option value="score">Best match</option>
            <option value="newest">Newest</option>
            <option value="company">Company</option>
          </select>
        </label>
      </div>

      <div className="flex items-center gap-2 px-4 py-2 sm:px-5">
        <div className="flex min-w-0 flex-1 items-center gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {(['Strong', 'Good', 'Stretch'] as Tier[]).map((tier) => (
            <FilterChip
              key={tier}
              label={tier}
              active={state.tiers.includes(tier as SearchState['tiers'][number])}
              color={TIER_COLOR[tier]}
              onClick={() => onStateChange({ tiers: toggle(state.tiers, tier as SearchState['tiers'][number]) }, { replace: true })}
            />
          ))}
          <span className="mx-0.5 h-5 w-px shrink-0 bg-line" aria-hidden="true" />
          {PRIMARY_FLAGS.map((flag) => (
            <FilterChip
              key={flag}
              label={FLAG_LABEL[flag]}
              ariaLabel={`Quick filter: ${FLAG_LABEL[flag]}`}
              active={state.flags.includes(flag)}
              onClick={() => onStateChange({ flags: toggle(state.flags, flag) }, { replace: true })}
            />
          ))}
        </div>
        <details className="group relative shrink-0">
          <summary className="flex h-8 cursor-pointer list-none items-center gap-1 rounded-full border border-line px-3 text-[11px] font-medium text-ink-2 transition hover:border-line-strong [&::-webkit-details-marker]:hidden">
            More<span className="hidden sm:inline"> filters</span>{advancedFilters ? ` · ${advancedFilters}` : ''}
            <ChevronDown size={13} aria-hidden="true" className="transition group-open:rotate-180" />
          </summary>
          <div className="fixed inset-x-3 top-40 z-30 max-h-[60vh] overflow-auto rounded-lg border border-line bg-panel p-4 shadow-xl sm:absolute sm:left-auto sm:right-0 sm:top-10 sm:w-[420px]">
            <div className="space-y-4">
              <fieldset>
                <legend className="mb-2 text-[10px] font-semibold uppercase text-ink-3">Quick filters</legend>
                <div className="flex flex-wrap gap-1.5">
                  {SECONDARY_FLAGS.map((flag) => (
                    <FilterChip
                      key={flag}
                      label={FLAG_LABEL[flag]}
                      ariaLabel={`Quick filter: ${FLAG_LABEL[flag]}`}
                      active={state.flags.includes(flag)}
                      onClick={() => onStateChange({ flags: toggle(state.flags, flag) }, { replace: true })}
                    />
                  ))}
                </div>
              </fieldset>
              {FACETS.map((facet) => {
                const values = uniqueFacetValues(rows, facet.get)
                if (!values.length) return null
                return (
                  <fieldset key={facet.key}>
                    <legend className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-ink-3">
                      {facet.label}
                    </legend>
                    <div className="flex flex-wrap gap-1.5">
                      {values.map((value) => (
                        <FilterChip
                          key={value}
                          label={value}
                          active={state[facet.key].includes(value)}
                          onClick={() =>
                            onStateChange(
                              { [facet.key]: toggle(state[facet.key], value) } as Partial<SearchState>,
                              { replace: true },
                            )
                          }
                        />
                      ))}
                    </div>
                  </fieldset>
                )
              })}
            </div>
            {activeFilters > 0 && (
              <button
                type="button"
                onClick={() =>
                  onStateChange(
                    { flags: [], tiers: [], resume: [], country: [], place: [], mode: [], funding: [], scope: [] },
                    { replace: true },
                  )
                }
                className="mt-4 text-[12px] font-medium text-brand hover:underline"
              >
                Clear all filters
              </button>
            )}
          </div>
        </details>
      </div>
    </div>
  )
}


function FilterChip({
  label,
  active,
  onClick,
  color,
  ariaLabel,
}: {
  label: string
  active: boolean
  onClick: () => void
  color?: string
  ariaLabel?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      className="h-8 shrink-0 rounded-full border px-3 text-[11px] font-medium transition"
      style={
        active
          ? { borderColor: color || 'var(--brand-coral)', color: color || 'var(--brand-coral)', background: 'var(--brand-weak)' }
          : { borderColor: 'var(--line)', color: 'var(--ink-2)', background: 'var(--panel)' }
      }
    >
      {label}
    </button>
  )
}

function FeedRow({ item, selected, onSelect }: { item: FeedItem; selected: boolean; onSelect: () => void }) {
  const { format } = useScoreFormat()
  const row = item.row
  const fit = presentFitRationale(row.rationale)
  return (
    <article
      data-feed-id={row.id}
      className={`group grid grid-cols-[minmax(0,1fr)_2.75rem] border-b border-line bg-panel transition-colors ${
        selected ? 'bg-brand-weak shadow-[inset_3px_0_var(--brand-coral)]' : 'hover:bg-inset/55'
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-label={`${row.company} — ${row.title}`}
        aria-current={selected ? 'true' : undefined}
        className="grid min-w-0 grid-cols-[3.5rem_minmax(0,1fr)] text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
      >
        <span className="flex flex-col items-center justify-start border-r border-line px-2 py-4">
          <span className="font-mono text-lg font-semibold tabular-nums" style={{ color: TIER_COLOR[row.tier] }}>
            {format === 'grade' ? scoreToGrade(row.score) : Math.round(row.score)}
          </span>
          <span className="mt-1 text-[9px] font-semibold uppercase" style={{ color: TIER_COLOR[row.tier] }}>
            {row.tier}
          </span>
        </span>
        <span className="min-w-0 px-4 py-3.5">
          <span className="flex items-start justify-between gap-3">
            <span className="min-w-0">
              <span className="block truncate text-[14px] font-semibold leading-5 text-ink">{row.title}</span>
              <span className="mt-0.5 block truncate text-[13px] text-ink-2">{row.company}</span>
            </span>
            {row.salary && <span className="hidden shrink-0 text-[11px] font-medium text-ink-2 sm:block">{row.salary}</span>}
          </span>
          <span className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-ink-3">
            {row.location && (
              <span className="inline-flex items-center gap-1"><MapPin size={11} aria-hidden="true" />{row.location}</span>
            )}
            {item.ageDays !== null && (
              <span className="inline-flex items-center gap-1"><Clock3 size={11} aria-hidden="true" />{item.ageDays === 0 ? 'today' : `${item.ageDays}d`}</span>
            )}
            {item.hasReferral && (
              <span className="inline-flex items-center gap-1 text-strong"><Users size={11} aria-hidden="true" />referral</span>
            )}
            {row.coverage_pct !== null && <span>{Math.round(row.coverage_pct)}% coverage</span>}
            {row.stale && <span className="text-stretch">stale</span>}
            {item.sourceNames.length > 0 && <span>{item.sourceNames.join(' + ')}</span>}
          </span>
          {fit.metrics.length > 0 ? (
            <span className="mt-2 block">
              <span className="flex flex-wrap gap-x-2.5 gap-y-0.5 text-[11px] text-ink-2">
                {fit.metrics.map((metric) => (
                  <span key={metric.label}>
                    {metric.label} <strong className="font-medium text-ink">{metric.value}%</strong>
                  </span>
                ))}
                {fit.company && <span>{fit.company} company</span>}
              </span>
              {fit.skills.length > 0 && (
                <span className="mt-1 line-clamp-1 block text-[11px] text-ink-3">
                  {fit.skills.slice(0, 5).join(' · ')}
                  {fit.skills.length > 5 ? ` +${fit.skills.length - 5}` : ''}
                </span>
              )}
            </span>
          ) : item.preview ? (
            <span className="mt-2 line-clamp-2 block text-[12px] leading-[1.45] text-ink-3">{item.preview}</span>
          ) : null}
        </span>
      </button>
      <a
        href={row.url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Apply to ${row.company} — ${row.title}`}
        title="Open application"
        className="flex items-center justify-center border-l border-line text-ink-3 outline-none transition hover:bg-brand-weak hover:text-brand focus-visible:bg-brand-weak focus-visible:text-brand"
      >
        <ArrowUpRight size={16} aria-hidden="true" />
      </a>
    </article>
  )
}

function FeedList({ model, selectedId, onSelect }: Pick<FeedViewProps, 'model' | 'selectedId' | 'onSelect'>) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtual = model.items.length > 50
  // TanStack Virtual intentionally returns mutable measurement callbacks.
  // eslint-disable-next-line react-hooks/incompatible-library
  const rowVirtualizer = useVirtualizer({
    count: virtual ? model.items.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 118,
    overscan: 6,
  })
  const virtualRows = rowVirtualizer.getVirtualItems()

  if (!model.items.length) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
        <BriefcaseBusiness size={28} strokeWidth={1.4} aria-hidden="true" className="text-ink-3" />
        <p className="mt-3 text-[14px] font-medium text-ink">No roles match this view</p>
        <p className="mt-1 text-[12px] text-ink-3">Clear a filter or broaden the search query.</p>
      </div>
    )
  }

  return (
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto" data-feed-scroll="">
      {virtual ? (
        <div className="relative w-full" style={{ height: rowVirtualizer.getTotalSize() }}>
          {virtualRows.map((virtualRow) => {
            const item = model.items[virtualRow.index]
            return (
              <div
                key={item.row.id}
                ref={rowVirtualizer.measureElement}
                data-index={virtualRow.index}
                className="absolute left-0 top-0 w-full"
                style={{ transform: `translateY(${virtualRow.start}px)` }}
              >
                <FeedRow item={item} selected={selectedId === item.row.id} onSelect={() => onSelect(item.row.id)} />
              </div>
            )
          })}
        </div>
      ) : (
        model.items.map((item) => (
          <FeedRow key={item.row.id} item={item} selected={selectedId === item.row.id} onSelect={() => onSelect(item.row.id)} />
        ))
      )}
    </div>
  )
}

export function FeedView(props: FeedViewProps) {
  const { model, onSelect, selectedId } = props
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target
      const typing =
        target instanceof HTMLElement &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return
      const key = event.key.toLowerCase()
      if (key !== 'j' && key !== 'k') return
      if (!model.items.length) return
      event.preventDefault()
      const current = model.items.findIndex((item) => item.row.id === selectedId)
      const next = key === 'j'
        ? Math.min(current < 0 ? 0 : current + 1, model.items.length - 1)
        : Math.max(current < 0 ? model.items.length - 1 : current - 1, 0)
      const id = model.items[next].row.id
      onSelect(id)
      requestAnimationFrame(() => {
        document.querySelector<HTMLElement>(`[data-feed-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest' })
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [model.items, onSelect, selectedId])
  return (
    <section aria-label="Ranked roles" className="flex min-h-0 min-w-0 flex-1 flex-col border-x border-line bg-panel lg:border-l lg:border-r-0">
      <FeedToolbar model={props.model} rows={props.model.facetRows} state={props.state} onStateChange={props.onStateChange} />
      <FeedList model={props.model} selectedId={props.selectedId} onSelect={props.onSelect} />
    </section>
  )
}

