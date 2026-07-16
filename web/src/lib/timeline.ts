// Timeline model for the v2 cockpit — a time-centric view: an "agenda" of what
// needs action now, plus the chronological track of the whole hunt bucketed by
// recency. Pure derivation over the emitted application timelines.

import type { DashboardData } from '@/lib/schema'
import type { ItemTone } from '@/lib/briefing'
import { daysSince, followupsDue, ghosted } from '@/lib/pipeline'

export type TimeBucket = 'today' | 'week' | 'month' | 'earlier'

export interface TimelineEvent {
  id: string
  date: string
  dateLabel: string
  signal: string
  text: string
  company: string
  jobId: string
  tone: ItemTone
}

export interface TimelineGroup {
  bucket: TimeBucket
  label: string
  events: TimelineEvent[]
}

export interface AgendaItem {
  id: string
  text: string
  when: string
  company: string
  jobId: string
  tone: ItemTone
}

export interface Timeline {
  agenda: AgendaItem[]
  groups: TimelineGroup[]
}

const SIGNAL_TEXT: Record<string, (c: string) => string> = {
  applied: (c) => `Applied to ${c}`,
  confirmation: (c) => `Application received by ${c}`,
  recruiter: (c) => `${c} recruiter reached out`,
  assessment: (c) => `Assessment from ${c}`,
  interview: (c) => `Interview step with ${c}`,
  offer: (c) => `Offer from ${c}`,
  rejection: (c) => `Passed by ${c}`,
}

const SIGNAL_TONE: Record<string, ItemTone> = {
  applied: 'neutral',
  confirmation: 'neutral',
  recruiter: 'neutral',
  assessment: 'good',
  interview: 'good',
  offer: 'brand',
  rejection: 'danger',
}

const BUCKET_LABEL: Record<TimeBucket, string> = {
  today: 'Today',
  week: 'This week',
  month: 'This month',
  earlier: 'Earlier',
}

function bucketOf(days: number): TimeBucket {
  if (days <= 0) return 'today'
  if (days < 7) return 'week'
  if (days < 31) return 'month'
  return 'earlier'
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function shortDate(iso: string, days: number): string {
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return `${days}d ago`
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`
}

export function buildTimeline(data: DashboardData, now = Date.now()): Timeline {
  const apps = data.applications ?? []

  // Agenda — the same "needs you" signals as the briefing, but framed by when.
  const agenda: AgendaItem[] = []
  for (const s of followupsDue(apps, now)) {
    const over = s.daysSinceApplied - 7
    agenda.push({
      id: `due:${s.app.job_id}`,
      text: `Follow up with ${s.app.company}`,
      when: over <= 0 ? 'Due now' : `${over}d overdue`,
      company: s.app.company,
      jobId: s.app.job_id,
      tone: 'stretch',
    })
  }
  for (const s of ghosted(apps, now)) {
    agenda.push({
      id: `ghost:${s.app.job_id}`,
      text: `${s.app.company} has gone quiet`,
      when: `${s.daysSinceApplied}d silent`,
      company: s.app.company,
      jobId: s.app.job_id,
      tone: 'danger',
    })
  }

  // History — submissions + real timeline events, newest first, bucketed.
  const events: TimelineEvent[] = []
  for (const a of apps) {
    const dApplied = daysSince(a.applied_at, now)
    if (dApplied !== null && dApplied >= 0) {
      events.push({
        id: `${a.job_id}:applied`,
        date: a.applied_at,
        dateLabel: shortDate(a.applied_at, dApplied),
        signal: 'applied',
        text: SIGNAL_TEXT.applied(a.company),
        company: a.company,
        jobId: a.job_id,
        tone: 'neutral',
      })
    }
    for (const [eventIndex, e] of (a.timeline ?? []).entries()) {
      const mk = SIGNAL_TEXT[e.signal]
      const d = daysSince(e.date, now)
      if (!mk || d === null || d < 0) continue
      events.push({
        id: `${a.job_id}:${e.signal}:${e.date}:${eventIndex}`,
        date: e.date,
        dateLabel: shortDate(e.date, d),
        signal: e.signal,
        text: mk(a.company),
        company: a.company,
        jobId: a.job_id,
        tone: SIGNAL_TONE[e.signal] ?? 'neutral',
      })
    }
  }
  events.sort((x, y) => (y.date > x.date ? 1 : y.date < x.date ? -1 : 0))

  const order: TimeBucket[] = ['today', 'week', 'month', 'earlier']
  const byBucket = new Map<TimeBucket, TimelineEvent[]>()
  for (const ev of events) {
    const d = daysSince(ev.date, now) ?? 9999
    const b = bucketOf(d)
    if (!byBucket.has(b)) byBucket.set(b, [])
    byBucket.get(b)!.push(ev)
  }
  const groups: TimelineGroup[] = order
    .filter((b) => (byBucket.get(b)?.length ?? 0) > 0)
    .map((b) => ({ bucket: b, label: BUCKET_LABEL[b], events: byBucket.get(b)! }))

  return { agenda, groups }
}
