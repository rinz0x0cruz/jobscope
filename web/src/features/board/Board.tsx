// The flagship "Board" surface — the whole job hunt as one warm Kanban pipeline.
// Purely presentational: it renders the already-derived `BoardColumn[]` (see
// `@/lib/board`) and reports card opens upward. No data fetching, no mutation.

import { useEffect, useRef, type ReactNode } from 'react'
import { AlarmClock, Clock, Mail, MapPin } from 'lucide-react'
import { Badge, animate, prefersReducedMotion } from '@/ui'
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

/**
 * Horizontal, scrollable Kanban of the pipeline. Each stage is a lane; each role
 * is a tappable card. On mount the cards fade + rise in a cheap staggered
 * entrance (skipped entirely under `prefers-reduced-motion`).
 */
export function Board({ columns, onOpen }: BoardProps) {
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
    <div ref={scrollerRef} className="flex h-[calc(100dvh-7rem)] gap-3 overflow-x-auto overflow-y-hidden lg:overflow-hidden">
      {columns.map((col) => (
        <section
          key={col.stage}
          className="flex w-[80vw] flex-none flex-col rounded-card bg-inset/60 p-2 sm:w-[46vw] lg:w-auto lg:min-w-0 lg:flex-1"
        >
          <header className="flex items-center gap-2 border-b border-line pb-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: col.color }}
              aria-hidden="true"
            />
            <span className="truncate text-sm font-semibold text-ink">{col.label}</span>
            <span className="ml-auto shrink-0">
              <Badge tone="neutral">{col.cards.length}</Badge>
            </span>
          </header>

          <div className="mt-2 flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto pr-0.5">
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
          <span className="truncate text-[13px] font-semibold text-ink">{card.company}</span>
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

      <p className="mt-0.5 line-clamp-1 text-[12px] leading-snug text-ink-2">{card.title}</p>

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
