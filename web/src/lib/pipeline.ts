import type { Application } from '@/lib/schema'

// "Pipeline health" derivations (issues #27 ghosting, #29 follow-ups, #28 timing).
// All computed client-side from the already-emitted application timeline — no
// change to the Python↔TS dashboard contract. Mirrors the funnel status model in
// components/applications/constants.ts.

/** Days after applying, with no reply, that a follow-up is due. Mirrors the
 *  backend default `apply.followup_days`. */
export const FOLLOWUP_DAYS = 7
/** No reply for this long reads as likely ghosted. Generic starting point, used
 *  only until your own reply history is large enough to measure — see
 *  {@link replyWindow}. */
export const GHOST_DAYS = 21
/** Replies needed before your own history is trusted over {@link GHOST_DAYS}. */
export const MIN_REPLY_SAMPLE = 5

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
 *  (newest-silent first), against the deadline your own repliers set. */
export function staleness(apps: Application[], now = Date.now()): StaleApp[] {
  const { windowDays } = replyWindow(apps)
  const out: StaleApp[] = []
  for (const app of apps) {
    if (!isAwaitingReply(app)) continue
    const dApplied = daysSince(app.applied_at || lastActivityAt(app), now) ?? 0
    const dAct = daysSince(lastActivityAt(app), now) ?? dApplied
    const bucket: StaleBucket =
      dApplied >= windowDays ? 'ghosted' : dApplied >= FOLLOWUP_DAYS ? 'due' : 'fresh'
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

/** Nearest-rank percentile: the smallest observed value that `p` of the samples
 *  fall at or below. No interpolation — these are whole days already. */
function percentile(nums: number[], p: number): number | null {
  if (nums.length === 0) return null
  const s = [...nums].sort((a, b) => a - b)
  return s[Math.min(s.length - 1, Math.ceil(p * s.length) - 1)]
}

export interface Timing {
  medianDaysToReply: number | null
  /** 90% of the replies you received arrived within this many days. */
  p90DaysToReply: number | null
  medianDaysToInterview: number | null
  replied: number
  interviewed: number
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
    p90DaysToReply: percentile(replyGaps, 0.9),
    medianDaysToInterview: median(ivGaps),
    replied: replyGaps.length,
    interviewed: ivGaps.length,
  }
}

export interface ReplyWindow {
  /** Applications that ever drew a real reply — the sample this rests on. */
  samples: number
  /** Silence past this many days reads as a no. */
  windowDays: number
  /** True once measured from your own replies instead of the generic default. */
  personalized: boolean
}

/** How long a reply actually takes *for you*.
 *
 *  A fixed 21-day ghost rule is a guess about employers in general. Once enough of
 *  them have actually replied, their slowest 10% is the real deadline — so an
 *  application stops sitting in "maybe" for weeks after the answer already arrived
 *  in the form of silence. Falls back to {@link GHOST_DAYS} until the sample is
 *  big enough to mean anything. */
export function replyWindow(apps: Application[]): ReplyWindow {
  const { replied, p90DaysToReply } = timing(apps)
  if (replied < MIN_REPLY_SAMPLE || p90DaysToReply === null) {
    return { samples: replied, windowDays: GHOST_DAYS, personalized: false }
  }
  // Never at or below the follow-up threshold, or the "due" bucket has no room.
  return {
    samples: replied,
    windowDays: Math.max(FOLLOWUP_DAYS + 1, p90DaysToReply),
    personalized: true,
  }
}
