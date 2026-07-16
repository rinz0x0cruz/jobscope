// The flagship "Board" surface — the whole job hunt as one warm Kanban pipeline.
// Purely presentational: it renders the already-derived `BoardColumn[]` (see
// `@/lib/board`) and reports card opens upward. No data fetching, no mutation.

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AlarmClock, ArrowRight, Clock, Mail, MapPin } from 'lucide-react'
import { Segmented, animate, prefersReducedMotion } from '@/ui'
import type { BoardCard, BoardColumn, BoardStage } from '@/lib/board'
import type { ActivityAudit, Tier } from '@/lib/schema'

export interface BoardProps {
  columns: BoardColumn[]
  onOpen: (jobId: string) => void
  audit?: ActivityAudit
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/** Tier → accent color (matches the funnel/legend hues). Drives the card's left
 *  rail and the tier micro-label. */
const TIER_COLOR: Record<Tier, string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}

type BoardView = 'list' | 'columns' | 'offers'
type ApplicationFilter = 'all' | BoardStage | 'attention'

/**
 * The Board surface: the applied pipeline as either a scannable table (default,
 * best for volume) or the stage-columned Kanban, toggled in the toolbar.
 */
export function Board({ columns, onOpen, audit }: BoardProps) {
  const [view, setView] = useState<BoardView>('list')
  const [filter, setFilter] = useState<ApplicationFilter>('all')
  const allCards = columns.flatMap((column) => column.cards)
  const total = allCards.length
  const attention = allCards.filter((card) => card.followup === 'due' || card.followup === 'ghosted')
  const visibleColumns = columns.map((column) => ({
    ...column,
    cards: column.cards.filter((card) => {
      if (filter === 'all') return true
      if (filter === 'attention') return card.followup === 'due' || card.followup === 'ghosted'
      return card.stage === filter
    }),
  }))
  const visibleTotal = visibleColumns.reduce((count, column) => count + column.cards.length, 0)
  // Roles with a recorded offer (offer stage, or comp/decision captured earlier),
  // gathered across stages for the side-by-side compare view.
  const offers = allCards
    .filter((c) => c.stage === 'offer' || c.salaryOffered || c.offerAccepted)
  const showOffers = view === 'offers' && offers.length > 0
  const latestReconciliation = audit?.recent_runs[0]
  const recoverableCount = audit?.recoverable_applications.length ?? 0
  return (
    <section className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col border-x border-line bg-panel">
      <header className="shrink-0 border-b border-line px-5 py-5 sm:px-7">
        <p className="text-[10px] font-semibold uppercase text-ink-3">Applications</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-ink">Application inbox</h2>
            <p className="mt-1 text-[13px] text-ink-3">Track outcomes, spot stalled conversations, and reopen any role.</p>
            {latestReconciliation && (
              <p className="mt-1 text-[11px] text-ink-3" aria-label="Last reconciliation">
                Last reconciliation · {latestReconciliation.applications_before} → {latestReconciliation.applications_after ?? '?'}
                {recoverableCount > 0
                  ? ` · ${recoverableCount} recoverable`
                  : ''}
              </p>
            )}
          </div>
          <strong className="font-mono text-2xl font-semibold text-ink">{total}</strong>
        </div>
      </header>

      <div className="flex shrink-0 overflow-x-auto border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Application filters">
        <SummaryFilter label="All" value={total} active={filter === 'all'} onClick={() => setFilter('all')} />
        {columns.map((column) => (
          <SummaryFilter
            key={column.stage}
            label={column.label}
            value={column.cards.length}
            color={column.color}
            active={filter === column.stage}
            onClick={() => setFilter(column.stage)}
          />
        ))}
        <SummaryFilter
          label="Needs attention"
          value={attention.length}
          color="var(--stretch)"
          active={filter === 'attention'}
          onClick={() => setFilter('attention')}
        />
      </div>

      <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-2 sm:px-7">
        <p aria-label={`${visibleTotal} shown`} className="text-[12px] text-ink-3">
          <span className="font-medium text-ink">{visibleTotal}</span> shown
          {attention.length > 0 && <span> · {attention.length} need follow-up</span>}
        </p>
        <Segmented
          ariaLabel="Board view"
          value={view}
          onChange={(v) => setView(v as BoardView)}
          options={[
            { value: 'list', label: 'List' },
            { value: 'columns', label: 'Board' },
            ...(offers.length ? [{ value: 'offers', label: 'Offers' }] : []),
          ]}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {showOffers ? (
          <OffersCompare offers={offers} onOpen={onOpen} />
        ) : view === 'columns' ? (
          <BoardColumns columns={visibleColumns} onOpen={onOpen} />
        ) : (
          <ApplicationList columns={visibleColumns} onOpen={onOpen} />
        )}
      </div>
    </section>
  )
}

function SummaryFilter({
  label,
  value,
  active,
  onClick,
  color = 'var(--brand-coral)',
}: {
  label: string
  value: number
  active: boolean
  onClick: () => void
  color?: string
}) {
  return (
    <button
      type="button"
      aria-label={`${label}: ${value}`}
      aria-pressed={active}
      onClick={onClick}
      className={`relative min-w-28 shrink-0 border-r border-line px-4 py-3 text-left transition-colors last:border-r-0 sm:min-w-32 ${
        active ? 'bg-inset' : 'hover:bg-inset/60'
      }`}
    >
      {active && <span className="absolute inset-x-0 bottom-0 h-0.5" style={{ background: color }} aria-hidden="true" />}
      <span className="block text-[10px] uppercase text-ink-3">{label}</span>
      <strong className="mt-0.5 block font-mono text-lg font-semibold" style={{ color: active ? color : 'var(--ink)' }}>
        {value}
      </strong>
    </button>
  )
}

/**
 * Offer comparison (#9): every role with a recorded offer, side by side — comp,
 * decision, next interview, and match tier — so competing offers are easy to weigh.
 * Each card opens the drawer, where the offer details are edited (local `serve`).
 */
function OffersCompare({ offers, onOpen }: { offers: BoardCard[]; onOpen: (jobId: string) => void }) {
  return (
    <div className="flex h-full gap-3 overflow-x-auto overflow-y-hidden p-3">
      {offers.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onOpen(o.id)}
          aria-label={`${o.company} — ${o.title}`}
          className="flex w-[80vw] flex-none flex-col gap-3 rounded-card border border-line bg-panel p-4 text-left outline-none transition-colors hover:bg-inset/60 focus-visible:bg-inset/60 sm:w-[300px]"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-ink">{o.company}</div>
            <div className="line-clamp-2 text-[12px] text-ink-3">{o.title}</div>
          </div>
          <OfferDecisionBadge decision={o.offerAccepted} />
          <dl className="grid gap-2 text-[13px]">
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-ink-3">Comp</dt>
              <dd className="font-medium text-ink">{o.salaryOffered || '\u2014'}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-ink-3">Next interview</dt>
              <dd className="text-ink-2">{o.interviewAt || '\u2014'}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wide text-ink-3">Match</dt>
              <dd className="text-ink-2">
                {o.tier ? <span style={{ color: TIER_COLOR[o.tier] }}>{o.tier}</span> : '\u2014'}
                {o.score != null ? ` \u00b7 ${o.score}` : ''}
              </dd>
            </div>
          </dl>
        </button>
      ))}
    </div>
  )
}

/** Colored pill for an offer decision (accepted / declined / pending), or a muted
 *  "No decision yet" when none is recorded. */
function OfferDecisionBadge({ decision }: { decision?: string }) {
  const map: Record<string, { label: string; color: string }> = {
    accepted: { label: 'Accepted', color: 'var(--good)' },
    declined: { label: 'Declined', color: 'var(--skip)' },
    pending: { label: 'Pending', color: 'var(--stretch)' },
  }
  const m = map[(decision || '').toLowerCase()]
  if (!m) return <span className="text-[11px] text-ink-3">No decision yet</span>
  return (
    <span
      className="inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ color: m.color, background: `color-mix(in srgb, ${m.color} 14%, transparent)` }}
    >
      {m.label}
    </span>
  )
}

/**
 * Horizontal, scrollable Kanban of the pipeline. Each stage is a lane; each role
 * is a tappable card. On mount the cards fade + rise in a cheap staggered
 * entrance (skipped entirely under `prefers-reduced-motion`).
 */
function BoardColumns({ columns, onOpen }: BoardProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    // Entrance stagger — runs once after the first paint. `animate` is a no-op
    // when the WAAPI is unavailable, so guard only for reduced motion here.
    if (prefersReducedMotion()) return
    const root = scrollerRef.current
    if (!root) return
    const cards = root.querySelectorAll<HTMLElement>('[data-board-card]')
    cards.forEach((el, i) => {
      animate(
        el,
        [
          { opacity: 0, transform: 'translateY(6px)' },
          { opacity: 1, transform: 'translateY(0)' },
        ],
        { duration: 220, delay: Math.min(i * 30, 300), easing: 'ease-out', fill: 'backwards' },
      )
    })
  }, [])

  return (
    <div ref={scrollerRef} className="flex h-full gap-3 overflow-x-auto overflow-y-hidden p-3 min-[1400px]:overflow-hidden">
      {columns.map((col) => (
        <section
          key={col.stage}
          className="flex w-[80vw] flex-none flex-col overflow-hidden rounded-card border border-line sm:w-[46vw] min-[1400px]:w-auto min-[1400px]:min-w-0 min-[1400px]:flex-1"
          style={{ background: `color-mix(in srgb, ${col.color} 5%, var(--panel))` }}
        >
          <span className="h-1 shrink-0" style={{ background: col.color }} aria-hidden="true" />
          <header className="flex items-center gap-2 px-3 py-2.5">
            <span className="truncate text-sm font-semibold text-ink">{col.label}</span>
            <span className="ml-auto shrink-0 rounded-full bg-panel px-2 py-0.5 text-[11px] font-semibold tabular-nums text-ink-2">
              {col.cards.length}
            </span>
          </header>

          <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto px-2 pb-2 pr-1.5">
            {col.cards.length === 0 ? (
              <p className="py-6 text-center text-xs text-ink-3">Nothing here yet</p>
            ) : (
              col.cards.map((card) => (
                <BoardCardButton key={card.id} card={card} onOpen={onOpen} />
              ))
            )}
          </div>
        </section>
      ))}
    </div>
  )
}

interface TableRow extends BoardCard {
  stageLabel: string
  stageColor: string
}

/** A scannable table of every application: company / role, stage, applied, signals.
 *  Fit/location live on the un-redacted match rows, which applied roles have
 *  aged out of, so they're intentionally omitted here (see the Kanban card for
 *  the richer per-role detail). */
function ApplicationList({ columns, onOpen }: BoardProps) {
  const rows: TableRow[] = columns.flatMap((col) =>
    col.cards.map((c) => ({ ...c, stageLabel: col.label, stageColor: col.color })),
  )
  if (rows.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <p className="text-[14px] font-medium text-ink">No applications in this view</p>
        <p className="mt-1 text-[12px] text-ink-3">Choose another stage or clear the attention filter.</p>
      </div>
    )
  }
  return (
    <div className="h-full overflow-auto">
      <div className="sticky top-0 z-10 hidden grid-cols-[minmax(0,1.5fr)_8rem_7rem_minmax(9rem,.7fr)_1.5rem] border-b border-line bg-inset px-6 py-2 text-[10px] font-semibold uppercase text-ink-3 sm:grid">
        <span>Role</span><span>Stage</span><span>Applied</span><span>Signals</span><span />
      </div>
      <ul>
        {rows.map((row) => (
          <li key={row.id} className="border-b border-line last:border-b-0">
            <button
              type="button"
              aria-label={`${row.company} — ${row.title}`}
              onClick={() => onOpen(row.id)}
              className="group relative grid w-full gap-2 px-5 py-3 text-left outline-none transition-colors hover:bg-inset/60 focus-visible:bg-inset sm:grid-cols-[minmax(0,1.5fr)_8rem_7rem_minmax(9rem,.7fr)_1.5rem] sm:items-center sm:px-6"
            >
              <span className="absolute inset-y-0 left-0 w-0.5" style={{ background: row.stageColor }} aria-hidden="true" />
              <span className="min-w-0">
                <span className="block truncate text-[14px] font-semibold text-ink">{row.title || row.company}</span>
                {row.title && <span className="block truncate text-[12px] text-ink-3">{row.company}</span>}
              </span>
              <span className="text-[11px] font-medium" style={{ color: row.stageColor }}>{row.stageLabel}</span>
              <span className="text-[12px] text-ink-2">
                {row.daysSinceApplied != null
                  ? row.daysSinceApplied === 0 ? 'today' : `${row.daysSinceApplied}d ago`
                  : '—'}
              </span>
              <TableSignals card={row} />
              <ArrowRight size={14} className="hidden text-ink-3 transition-transform group-hover:translate-x-0.5 sm:block" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Compact signal chips for a table row (follow-up / ghosted / HR contact / emails). */
function TableSignals({ card }: { card: BoardCard }) {
  const items: ReactNode[] = []
  if (card.followup === 'due') {
    items.push(
      <span key="due" className="inline-flex items-center gap-1" style={{ color: 'var(--stretch)' }}>
        <Clock size={13} aria-hidden="true" />
        Follow up
      </span>,
    )
  }
  if (card.followup === 'ghosted') {
    items.push(
      <span key="ghost" className="inline-flex items-center gap-1" style={{ color: 'var(--hot)' }}>
        <AlarmClock size={13} aria-hidden="true" />
        Ghosted
      </span>,
    )
  }
  if (card.outreach) {
    items.push(
      <span key="hr" className="inline-flex items-center gap-1 text-brand">
        <Mail size={13} aria-hidden="true" />
        HR
      </span>,
    )
  }
  if (card.emails && card.emails > 0) {
    items.push(
      <span key="mail" className="inline-flex items-center gap-1 text-ink-3">
        <Mail size={13} aria-hidden="true" />
        {card.emails}
      </span>,
    )
  }
  if (items.length === 0) return <span className="text-ink-3">—</span>
  return <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px]">{items}</div>
}

interface BoardCardButtonProps {
  card: BoardCard
  onOpen: (jobId: string) => void
}

function BoardCardButton({ card, onOpen }: BoardCardButtonProps) {
  const meta: Array<{ key: string; node: ReactNode }> = []
  if (card.location) {
    meta.push({
      key: 'loc',
      node: (
        <>
          <MapPin size={12} className="shrink-0" aria-hidden="true" />
          <span>{card.location}</span>
        </>
      ),
    })
  }
  if (card.score != null) {
    meta.push({ key: 'score', node: <span>{card.score}</span> })
  }
  if (card.daysSinceApplied != null) {
    meta.push({
      key: 'applied',
      node: (
        <span>applied {card.daysSinceApplied === 0 ? 'today' : `${card.daysSinceApplied}d ago`}</span>
      ),
    })
  }

  const flags: Array<{ key: string; className: string; icon: ReactNode; label: ReactNode }> = []
  if (card.followup === 'due') {
    flags.push({
      key: 'due',
      className: 'bg-[#f6e4c8] text-[#8a5a00]',
      icon: <Clock size={12} aria-hidden="true" />,
      label: 'Follow up',
    })
  }
  if (card.followup === 'ghosted') {
    flags.push({
      key: 'ghosted',
      className: 'bg-[#f7ddd8] text-[#a83a2c]',
      icon: <AlarmClock size={12} aria-hidden="true" />,
      label: 'Ghosted',
    })
  }
  if (card.outreach) {
    flags.push({
      key: 'outreach',
      className: 'bg-brand-weak text-brand',
      icon: <Mail size={12} aria-hidden="true" />,
      label: 'HR contact',
    })
  }
  if (card.emails && card.emails > 0) {
    flags.push({
      key: 'emails',
      className: 'bg-inset text-ink-3',
      icon: <Mail size={12} aria-hidden="true" />,
      label: card.emails,
    })
  }

  const railColor = card.tier ? TIER_COLOR[card.tier] : 'var(--line-strong)'

  return (
    <button
      type="button"
      data-board-card=""
      onClick={() => onOpen(card.id)}
      aria-label={`${card.company} — ${card.title}`}
      className={cx(
        'group relative w-full shrink-0 overflow-hidden rounded-card border border-line bg-panel',
        'py-2 pl-3 pr-2.5 text-left',
        'shadow-[0_1px_2px_rgba(29,27,24,0.04)] transition-all duration-200 ease-[cubic-bezier(.2,0,0,1)]',
        'hover:-translate-y-0.5 hover:border-line-strong hover:shadow-[var(--shadow-panel)]',
        'outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-paper',
      )}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1 rounded-r-full opacity-80 transition-opacity group-hover:opacity-100"
        style={{ background: railColor }}
      />

      <div className="flex items-baseline justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-[13px] font-semibold text-ink">{card.title || card.company}</span>
        </span>
        {card.tier && (
          <span
            className="shrink-0 text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: TIER_COLOR[card.tier] }}
          >
            {card.tier}
          </span>
        )}
      </div>

      {card.title && (
        <p className="mt-0.5 line-clamp-1 text-[12px] leading-snug text-ink-2">{card.company}</p>
      )}

      {meta.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-ink-3">
          {meta.map((m, i) => (
            <span key={m.key} className="inline-flex items-center gap-1">
              {i > 0 && <span aria-hidden="true">·</span>}
              {m.node}
            </span>
          ))}
        </div>
      )}

      {flags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {flags.map((f) => (
            <span
              key={f.key}
              className={cx(
                'inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                f.className,
              )}
            >
              {f.icon}
              {f.label}
            </span>
          ))}
        </div>
      )}
    </button>
  )
}
