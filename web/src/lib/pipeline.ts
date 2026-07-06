import type { Application } from '@/lib/schema'

// "Pipeline health" derivations (issues #27 ghosting, #29 follow-ups, #28 timing).
// All computed client-side from the already-emitted application timeline — no
// change to the Python↔TS dashboard contract. Mirrors the funnel status model in
// components/applications/constants.ts.

/** Days after applying, with no reply, that a follow-up is due. Mirrors the
 *  backend default `apply.followup_days`. */
export const FOLLOWUP_DAYS = 7
/** No reply for this long reads as likely ghosted. */
export const GHOST_DAYS = 21

const DAY = 86_400_000
// A genuine reply (not the automated "application received" confirmation).
const RESPONSE_SIGNALS = new Set(['recruiter', 'assessment', 'interview', 'offer', 'rejection'])
const INTERVIEW_SIGNALS = new Set(['assessment', 'interview'])

function parse(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : t
}

/** Whole days since an ISO timestamp (null if unparseable). */
export function daysSince(iso: string | null | undefined, now = Date.now()): number | null {
  const t = parse(iso)
  return t === null ? null : Math.floor((now - t) / DAY)
}

/** Newest timeline event date, falling back to applied_at / updated. */
export function lastActivityAt(app: Application): string | null {
  const dates = (app.timeline ?? []).map((e) => e.date).filter(Boolean)
  const newest = dates.sort().at(-1)
  return newest ?? app.applied_at ?? app.updated ?? null
}

function hasResponse(app: Application): boolean {
  return (app.timeline ?? []).some((e) => RESPONSE_SIGNALS.has(e.signal))
}

/** Submitted, but still no advancing reply (funnel stuck at "applied"). These are
 *  the follow-up / ghosting candidates. */
export function isAwaitingReply(app: Application): boolean {
  return (app.status || '') === 'applied' && !hasResponse(app)
}

export type StaleBucket = 'fresh' | 'due' | 'ghosted'

export interface StaleApp {
  app: Application
  daysSinceApplied: number
  daysSinceActivity: number
  bucket: StaleBucket
}

/** Every awaiting-reply application, bucketed by how long it has been silent
 *  (newest-silent first). */
export function staleness(apps: Application[], now = Date.now()): StaleApp[] {
  const out: StaleApp[] = []
  for (const app of apps) {
    if (!isAwaitingReply(app)) continue
    const dApplied = daysSince(app.applied_at || lastActivityAt(app), now) ?? 0
    const dAct = daysSince(lastActivityAt(app), now) ?? dApplied
    const bucket: StaleBucket =
      dApplied >= GHOST_DAYS ? 'ghosted' : dApplied >= FOLLOWUP_DAYS ? 'due' : 'fresh'
    out.push({ app, daysSinceApplied: dApplied, daysSinceActivity: dAct, bucket })
  }
  return out.sort((a, b) => b.daysSinceApplied - a.daysSinceApplied)
}

/** Applications past the follow-up window but not yet ghosted (#29). */
export function followupsDue(apps: Application[], now = Date.now()): StaleApp[] {
  return staleness(apps, now).filter((s) => s.bucket === 'due')
}

/** Applications silent long enough to read as ghosted (#27). */
export function ghosted(apps: Application[], now = Date.now()): StaleApp[] {
  return staleness(apps, now).filter((s) => s.bucket === 'ghosted')
}

function firstEventDate(app: Application, signals: Set<string>): number | null {
  let best: number | null = null
  for (const e of app.timeline ?? []) {
    if (!signals.has(e.signal)) continue
    const t = parse(e.date)
    if (t !== null && (best === null || t < best)) best = t
  }
  return best
}

function median(nums: number[]): number | null {
  if (nums.length === 0) return null
  const s = [...nums].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2)
}

export interface Timing {
  medianDaysToReply: number | null
  medianDaysToInterview: number | null
  replied: number
}

/** Median days from applying to the first real reply and to the first interview
 *  step, across applications that got that far (#28). */
export function timing(apps: Application[]): Timing {
  const replyGaps: number[] = []
  const ivGaps: number[] = []
  for (const app of apps) {
    const applied = parse(app.applied_at)
    if (applied === null) continue
    const reply = firstEventDate(app, RESPONSE_SIGNALS)
    if (reply !== null && reply >= applied) replyGaps.push(Math.round((reply - applied) / DAY))
    const iv = firstEventDate(app, INTERVIEW_SIGNALS)
    if (iv !== null && iv >= applied) ivGaps.push(Math.round((iv - applied) / DAY))
  }
  return {
    medianDaysToReply: median(replyGaps),
    medianDaysToInterview: median(ivGaps),
    replied: replyGaps.length,
  }
}
