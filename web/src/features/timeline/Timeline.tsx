// The "Timeline" lens — a time-centric view of the whole hunt. Purely
// presentational: it renders an already-derived `Timeline` (see `@/lib/timeline`)
// as a short "Up next" agenda of what needs action, then the chronological track
// of everything as a classic vertical timeline (a spine with dots) grouped by
// recency. Reports role opens upward. No data fetching, no mutation.

import { ArrowRight, CalendarClock, History, Inbox } from 'lucide-react'
import type { ItemTone } from '@/lib/briefing'
import type { ActivityAudit } from '@/lib/schema'
import type { AgendaItem, TimelineGroup, Timeline as TimelineData } from '@/lib/timeline'
import { ReconciliationAudit } from './ReconciliationAudit'

export interface TimelineProps {
  timeline: TimelineData
  onOpen: (jobId: string) => void
  audit?: ActivityAudit
  onRecover?: (jobId: string) => void
}

const EMPTY_AUDIT: ActivityAudit = {
  recent_runs: [],
  selected_run_id: '',
  decisions: [],
  recoverable_applications: [],
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
      className="group relative grid w-full grid-cols-[3px_minmax(0,1fr)_auto] items-center gap-3 border-b border-line px-5 py-3 text-left outline-none transition-colors last:border-b-0 hover:bg-inset/60 focus-visible:bg-inset sm:px-6"
    >
      <span className="h-8 rounded-full" style={{ background: TONE_COLOR[item.tone] }} aria-hidden="true" />
      <span className="min-w-0">
        <span className="block truncate text-[14px] font-medium text-ink">{item.text}</span>
        <span className="mt-0.5 block truncate text-[11px] text-ink-3">{item.company}</span>
      </span>
      <span
        className="shrink-0 text-[11px] font-semibold"
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
  return (
    <section aria-labelledby={`activity-${group.bucket}`}>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-inset px-5 py-2 sm:px-7">
        <h3 id={`activity-${group.bucket}`} className="text-[10px] font-semibold uppercase text-ink-3">{group.label}</h3>
        <span className="font-mono text-[11px] text-ink-3">{group.events.length}</span>
      </header>
      <ol>
        {group.events.map((event) => (
          <li key={event.id} className="border-b border-line last:border-b-0">
            <button
              type="button"
              onClick={() => onOpen(event.jobId)}
              aria-label={`${event.text}, ${event.dateLabel}`}
              className="group grid w-full grid-cols-[4.5rem_minmax(0,1fr)_1.5rem] items-center gap-3 px-5 py-3 text-left outline-none transition-colors hover:bg-inset/60 focus-visible:bg-inset sm:grid-cols-[5.5rem_minmax(0,1fr)_7rem_1.5rem] sm:px-7"
            >
              <span className="text-[11px] text-ink-3">{event.dateLabel}</span>
              <span className="min-w-0">
                <span className="block truncate text-[14px] text-ink transition-colors">{event.text}</span>
                <span className="mt-0.5 block text-[10px] font-semibold uppercase" style={{ color: TONE_COLOR[event.tone] }}>
                  {event.signal}
                </span>
              </span>
              <span className="hidden truncate text-right text-[12px] text-ink-3 sm:block">{event.company}</span>
              <ArrowRight size={14} className="text-ink-3 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
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
export function Timeline({
  timeline,
  onOpen,
  audit = EMPTY_AUDIT,
  onRecover = () => {},
}: TimelineProps) {
  const { agenda, groups } = timeline

  if (agenda.length === 0 && groups.length === 0) {
    return (
      <section className="mx-auto flex h-full max-w-[1600px] flex-col border-x border-line bg-panel">
        <header className="border-b border-line px-5 py-5 sm:px-7">
          <p className="text-[10px] font-semibold uppercase text-ink-3">Activity</p>
          <h2 className="mt-1 text-xl font-semibold text-ink">Actions and history</h2>
        </header>
        <ReconciliationAudit audit={audit} onRecover={onRecover} />
        <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
          <Inbox className="h-8 w-8 text-ink-3" strokeWidth={1.5} aria-hidden="true" />
          <p className="mt-4 max-w-sm text-[14px] text-ink-3">
            No activity yet — your applications and their replies will appear here as a timeline.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col border-x border-line bg-panel">
      <header className="shrink-0 border-b border-line px-5 py-5 sm:px-7">
        <p className="text-[10px] font-semibold uppercase text-ink-3">Activity</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-ink">Actions and history</h2>
            <p className="mt-1 text-[13px] text-ink-3">Work overdue follow-ups, then review every application signal in order.</p>
          </div>
          <div className="flex gap-5 text-right">
            <div><span className="block text-[10px] uppercase text-ink-3">Actions</span><strong className="font-mono text-xl text-ink">{agenda.length}</strong></div>
            <div><span className="block text-[10px] uppercase text-ink-3">Events</span><strong className="font-mono text-xl text-ink">{groups.reduce((count, group) => count + group.events.length, 0)}</strong></div>
          </div>
        </div>
      </header>

      <ReconciliationAudit audit={audit} onRecover={onRecover} />

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(320px,.72fr)_minmax(0,1.28fr)]">
        <aside className="min-h-0 border-b border-line lg:border-b-0 lg:border-r" aria-label="Action queue">
          <div className="flex items-center justify-between border-b border-line bg-inset px-5 py-2 sm:px-6">
            <h3 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-ink-3">
              <CalendarClock size={13} aria-hidden="true" /> Action queue
            </h3>
            <span className="font-mono text-[11px] text-ink-3">{agenda.length}</span>
          </div>
          <div className="max-h-72 overflow-auto lg:max-h-none lg:h-[calc(100%-2.25rem)]">
            {agenda.length > 0 ? (
              <ul>
                {agenda.map((item) => <li key={item.id}><AgendaRow item={item} onOpen={onOpen} /></li>)}
              </ul>
            ) : (
              <p className="px-6 py-10 text-center text-[13px] text-ink-3">Nothing needs action right now.</p>
            )}
          </div>
        </aside>

        <div className="min-h-0 overflow-auto" aria-label="Activity stream">
          <div className="flex items-center justify-between border-b border-line bg-inset px-5 py-2 sm:px-7">
            <h3 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-ink-3">
              <History size={13} aria-hidden="true" /> Event stream
            </h3>
          </div>
          {groups.map((group) => <GroupSection key={group.bucket} group={group} onOpen={onOpen} />)}
        </div>
      </div>
    </section>
  )
}
