// The "Timeline" lens — a time-centric view of the whole hunt. Purely
// presentational: it renders an already-derived `Timeline` (see `@/lib/timeline`)
// as a short "Up next" agenda of what needs action, then the chronological track
// of everything as a classic vertical timeline (a spine with dots) grouped by
// recency. Reports role opens upward. No data fetching, no mutation.

import { CalendarClock, Inbox } from 'lucide-react'
import type { ItemTone } from '@/lib/briefing'
import type { AgendaItem, TimelineGroup, Timeline as TimelineData } from '@/lib/timeline'

export interface TimelineProps {
  timeline: TimelineData
  onOpen: (jobId: string) => void
}

/** ItemTone → accent color (theme var) for the dots, pills and spine markers. */
const TONE_COLOR: Record<ItemTone, string> = {
  brand: 'var(--brand-coral)',
  good: 'var(--good)',
  stretch: 'var(--stretch)',
  danger: 'var(--hot)',
  neutral: 'var(--ink-3)',
}

/** An "Up next" row: a toned dot + the ask on the left, a toned "when" pill on
 *  the right. The whole row is a button that opens the underlying role. */
function AgendaRow({ item, onOpen }: { item: AgendaItem; onOpen: (jobId: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(item.jobId)}
      className="-mx-2 flex w-full items-center justify-between gap-3 rounded-card px-2 py-2 text-left transition-colors hover:bg-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
    >
      <span className="flex min-w-0 items-center gap-2.5">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: TONE_COLOR[item.tone] }}
          aria-hidden="true"
        />
        <span className="truncate text-[14px] text-ink">{item.text}</span>
      </span>
      <span
        className="shrink-0 rounded-full bg-inset px-2 py-0.5 text-[11px] font-semibold"
        style={{ color: TONE_COLOR[item.tone] }}
      >
        {item.when}
      </span>
    </button>
  )
}

/** A recency group as a vertical timeline: a small label, then a spine where each
 *  event is a toned dot connected by a hairline down to the next, beside a
 *  clickable line of copy with its relative date. */
function GroupSection({ group, onOpen }: { group: TimelineGroup; onOpen: (jobId: string) => void }) {
  const last = group.events.length - 1
  return (
    <section>
      <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
        {group.label}
      </h2>
      <ol className="relative">
        {group.events.map((event, i) => (
          <li key={event.id} className="relative flex gap-3 pl-1">
            <div className="relative flex w-4 shrink-0 justify-center">
              {i < last && (
                <span
                  className="absolute left-1/2 top-4 h-full w-px -translate-x-1/2 bg-line"
                  aria-hidden="true"
                />
              )}
              <span
                className="relative z-10 mt-3 h-2.5 w-2.5 rounded-full ring-4 ring-paper"
                style={{ background: TONE_COLOR[event.tone] }}
                aria-hidden="true"
              />
            </div>
            <button
              type="button"
              onClick={() => onOpen(event.jobId)}
              className="group flex flex-1 items-baseline justify-between gap-3 rounded-card py-2 pr-1 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
            >
              <span className="text-[14px] text-ink-2 transition-colors group-hover:text-ink">
                {event.text}
              </span>
              <span className="shrink-0 text-[12px] text-ink-3">{event.dateLabel}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

/**
 * The Timeline lens: a single centered column — an "Up next" agenda card of what
 * needs action, followed by the chronological history of the hunt rendered as a
 * classic vertical timeline, grouped by recency.
 */
export function Timeline({ timeline, onOpen }: TimelineProps) {
  const { agenda, groups } = timeline

  if (agenda.length === 0 && groups.length === 0) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="flex flex-col items-center justify-center rounded-card border border-line bg-panel px-6 py-16 text-center shadow-[var(--shadow-panel)]">
          <Inbox className="h-8 w-8 text-ink-3" strokeWidth={1.5} aria-hidden="true" />
          <p className="mt-4 max-w-sm text-[14px] text-ink-3">
            No activity yet — your applications and their replies will appear here as a timeline.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      {agenda.length > 0 && (
        <section className="rounded-card border border-line bg-panel p-4 shadow-[var(--shadow-panel)]">
          <h2 className="mb-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
            <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Up next</span>
          </h2>
          <ul className="space-y-0.5">
            {agenda.map((item) => (
              <li key={item.id}>
                <AgendaRow item={item} onOpen={onOpen} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {groups.map((group) => (
        <GroupSection key={group.bucket} group={group} onOpen={onOpen} />
      ))}
    </div>
  )
}
