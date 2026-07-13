// The flagship "Board" surface — the whole job hunt as one warm Kanban pipeline.
// Purely presentational: it renders the already-derived `BoardColumn[]` (see
// `@/lib/board`) and reports card opens upward. No data fetching, no mutation.

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AlarmClock, Clock, Mail, MapPin } from 'lucide-react'
import { Segmented, animate, prefersReducedMotion } from '@/ui'
import type { BoardCard, BoardColumn } from '@/lib/board'
import type { Tier } from '@/lib/schema'

export interface BoardProps {
  columns: BoardColumn[]
  onOpen: (jobId: string) => void
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

type BoardView = 'table' | 'columns' | 'offers'

/**
 * The Board surface: the applied pipeline as either a scannable table (default,
 * best for volume) or the stage-columned Kanban, toggled in the toolbar.
 */
export function Board({ columns, onOpen }: BoardProps) {
  const [view, setView] = useState<BoardView>('table')
  const total = columns.reduce((n, col) => n + col.cards.length, 0)
  // Roles with a recorded offer (offer stage, or comp/decision captured earlier),
  // gathered across stages for the side-by-side compare view.
  const offers = columns
    .flatMap((col) => col.cards)
    .filter((c) => c.stage === 'offer' || c.salaryOffered || c.offerAccepted)
  const showOffers = view === 'offers' && offers.length > 0
  return (
    <div className="flex h-[calc(100dvh-7rem)] flex-col gap-3">
      <div className="flex shrink-0 items-center justify-between gap-3">
        <p className="text-sm text-ink-3">
          {total} {total === 1 ? 'application' : 'applications'}
        </p>
        <Segmented
          ariaLabel="Board view"
          value={view}
          onChange={(v) => setView(v as BoardView)}
          options={[
            { value: 'table', label: 'Table' },
            { value: 'columns', label: 'Columns' },
            ...(offers.length ? [{ value: 'offers', label: 'Offers' }] : []),
          ]}
        />
      </div>
      <div className="min-h-0 flex-1">
        {showOffers ? (
          <OffersCompare offers={offers} onOpen={onOpen} />
        ) : view === 'columns' ? (
          <BoardColumns columns={columns} onOpen={onOpen} />
        ) : (
          <BoardTable columns={columns} onOpen={onOpen} />
        )}
      </div>
    </div>
  )
}

/**
 * Offer comparison (#9): every role with a recorded offer, side by side — comp,
 * decision, next interview, and match tier — so competing offers are easy to weigh.
 * Each card opens the drawer, where the offer details are edited (local `serve`).
 */
function OffersCompare({ offers, onOpen }: { offers: BoardCard[]; onOpen: (jobId: string) => void }) {
  return (
    <div className="flex h-full gap-3 overflow-x-auto overflow-y-hidden pb-1">
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
    <div ref={scrollerRef} className="flex h-full gap-3 overflow-x-auto overflow-y-hidden lg:overflow-hidden">
      {columns.map((col) => (
        <section
          key={col.stage}
          className="flex w-[80vw] flex-none flex-col overflow-hidden rounded-card border border-line sm:w-[46vw] lg:w-auto lg:min-w-0 lg:flex-1"
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
function BoardTable({ columns, onOpen }: BoardProps) {
  const rows: TableRow[] = columns.flatMap((col) =>
    col.cards.map((c) => ({ ...c, stageLabel: col.label, stageColor: col.color })),
  )
  if (rows.length === 0) {
    return <p className="py-16 text-center text-sm text-ink-3">No applications yet</p>
  }
  return (
    <div className="h-full overflow-auto rounded-card border border-line">
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-inset">
          <tr className="text-left text-[11px] uppercase tracking-wide text-ink-3">
            <th className="px-3 py-2.5 font-semibold">Role</th>
            <th className="px-3 py-2.5 font-semibold">Stage</th>
            <th className="whitespace-nowrap px-3 py-2.5 font-semibold">Applied</th>
            <th className="px-3 py-2.5 font-semibold">Signals</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr
              key={r.id}
              role="button"
              tabIndex={0}
              aria-label={`${r.company} — ${r.title}`}
              onClick={() => onOpen(r.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onOpen(r.id)
                }
              }}
              className="cursor-pointer bg-panel outline-none transition-colors hover:bg-inset/60 focus-visible:bg-inset/60"
            >
              <td className="px-3 py-2.5">
                <div className="font-semibold text-ink">{r.title || r.company}</div>
                {r.title && <div className="line-clamp-1 text-[12px] text-ink-3">{r.company}</div>}
              </td>
              <td className="px-3 py-2.5">
                <span
                  className="inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium"
                  style={{
                    color: r.stageColor,
                    background: `color-mix(in srgb, ${r.stageColor} 14%, transparent)`,
                  }}
                >
                  {r.stageLabel}
                </span>
              </td>
              <td className="whitespace-nowrap px-3 py-2.5 text-ink-2">
                {r.daysSinceApplied != null
                  ? r.daysSinceApplied === 0
                    ? 'today'
                    : `${r.daysSinceApplied}d ago`
                  : '—'}
              </td>
              <td className="px-3 py-2.5">
                <TableSignals card={r} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
