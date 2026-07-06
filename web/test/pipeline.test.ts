import { describe, it, expect } from 'vitest'
import type { Application } from '@/lib/schema'
import {
  daysSince,
  isAwaitingReply,
  staleness,
  followupsDue,
  ghosted,
  timing,
  FOLLOWUP_DAYS,
  GHOST_DAYS,
} from '@/lib/pipeline'

const NOW = Date.parse('2026-07-07T00:00:00Z')
const daysAgo = (n: number) => new Date(NOW - n * 86_400_000).toISOString()

const app = (p: Partial<Application>): Application => ({
  job_id: p.job_id ?? 'j' + Math.random().toString(36).slice(2),
  company: p.company ?? 'Acme',
  title: p.title ?? 'Engineer',
  status: p.status ?? 'applied',
  applied_at: p.applied_at ?? '',
  updated: p.updated ?? '',
  source: p.source ?? 'inbox',
  timeline: p.timeline ?? [],
})
const ev = (date: string, signal: string) => ({ date, signal, subject: '', from: '', summary: '' })

describe('pipeline: daysSince', () => {
  it('floors whole days and rejects bad input', () => {
    expect(daysSince(daysAgo(3), NOW)).toBe(3)
    expect(daysSince('', NOW)).toBeNull()
    expect(daysSince('nope', NOW)).toBeNull()
  })
})

describe('pipeline: awaiting reply (#27/#29 candidates)', () => {
  it('is true for applied with only an automated confirmation', () => {
    expect(isAwaitingReply(app({ status: 'applied', timeline: [ev(daysAgo(5), 'confirmation')] }))).toBe(true)
  })
  it('is false once a real reply arrives or the status advances', () => {
    expect(isAwaitingReply(app({ status: 'applied', timeline: [ev(daysAgo(2), 'recruiter')] }))).toBe(false)
    expect(isAwaitingReply(app({ status: 'interview' }))).toBe(false)
    expect(isAwaitingReply(app({ status: 'rejected' }))).toBe(false)
  })
})

describe('pipeline: staleness buckets (#27 ghosting, #29 follow-ups)', () => {
  const apps = [
    app({ company: 'Fresh', status: 'applied', applied_at: daysAgo(3) }),
    app({ company: 'Due', status: 'applied', applied_at: daysAgo(FOLLOWUP_DAYS + 2) }),
    app({ company: 'Ghost', status: 'applied', applied_at: daysAgo(GHOST_DAYS + 5) }),
    // A real reply -> no longer awaiting, even though old.
    app({ company: 'Replied', status: 'applied', applied_at: daysAgo(30), timeline: [ev(daysAgo(1), 'recruiter')] }),
    app({ company: 'Interviewing', status: 'interview', applied_at: daysAgo(30) }),
  ]

  it('buckets awaiting apps by silence, longest-silent first', () => {
    const s = staleness(apps, NOW)
    expect(s.map((x) => x.app.company)).toEqual(['Ghost', 'Due', 'Fresh'])
    expect(s.map((x) => x.bucket)).toEqual(['ghosted', 'due', 'fresh'])
  })

  it('followupsDue / ghosted select the right buckets', () => {
    expect(followupsDue(apps, NOW).map((x) => x.app.company)).toEqual(['Due'])
    expect(ghosted(apps, NOW).map((x) => x.app.company)).toEqual(['Ghost'])
  })
})

describe('pipeline: timing (#28)', () => {
  it('computes median days to first reply and to interview', () => {
    const apps = [
      app({
        applied_at: daysAgo(20),
        timeline: [ev(daysAgo(18), 'confirmation'), ev(daysAgo(14), 'recruiter'), ev(daysAgo(10), 'interview')],
      }),
      app({ applied_at: daysAgo(10), timeline: [ev(daysAgo(8), 'assessment')] }),
      app({ applied_at: daysAgo(5), timeline: [] }),
    ]
    const t = timing(apps)
    expect(t.replied).toBe(2)
    expect(t.medianDaysToReply).toBe(4) // median of [6, 2]
    expect(t.medianDaysToInterview).toBe(6) // median of [10, 2]
  })

  it('returns null medians when nothing has replied', () => {
    const t = timing([app({ applied_at: daysAgo(3), timeline: [ev(daysAgo(2), 'confirmation')] })])
    expect(t.medianDaysToReply).toBeNull()
    expect(t.medianDaysToInterview).toBeNull()
  })
})
