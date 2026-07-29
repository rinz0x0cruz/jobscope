import { pct, pipelineMetrics } from '@/components/applications/constants'
import type { EngagementThread } from '@/lib/campaigns'
import { replyWindow, staleness, timing } from '@/lib/pipeline'
import type { Application } from '@/lib/schema'

const DAY = 86_400_000
export const MIN_ANALYTICS_SAMPLE = 3
const DELIVERED_STATES = new Set(['sent', 'replied', 'opted_out'])
const UNKNOWN_DELIVERY_STATES = new Set(['delivery_unknown', 'sending'])

export interface RateMetric {
  numerator: number
  denominator: number
  percent: number
}

export interface ApplicationAnalytics {
  submitted: number
  reachedInterview: number
  offers: number
  rejected: number
  awaitingReply: number
  needsAttention: number
  interviewRate: RateMetric
  offerRate: RateMetric
  timing: ReturnType<typeof timing>
  /** The silence deadline your own repliers set, and whether it is measured yet. */
  replyWindow: ReturnType<typeof replyWindow>
  /** Awaiting a reply for longer than any employer has ever taken to send one. */
  pastReplyWindow: number
  sufficient: boolean
}

export interface OutreachCohort {
  sentThreads: number
  repliedThreads: number
  responseRate: RateMetric
}

export interface OutreachAnalytics extends OutreachCohort {
  followupsSent: number
  awaitingReply: number
  optOuts: number
  deliveryUnknown: number
  medianDaysToReply: number | null
  cohorts: {
    cold: OutreachCohort
    application: OutreachCohort
  }
  sufficient: boolean
}

function rate(numerator: number, denominator: number): RateMetric {
  return { numerator, denominator, percent: pct(numerator, denominator) }
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const ordered = [...values].sort((left, right) => left - right)
  const middle = Math.floor(ordered.length / 2)
  return ordered.length % 2
    ? ordered[middle]
    : Math.round((ordered[middle - 1] + ordered[middle]) / 2)
}

function timestamp(value: string): number | null {
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

export function applicationAnalytics(applications: Application[], now = Date.now()): ApplicationAnalytics {
  const metrics = pipelineMetrics(applications)
  const stale = staleness(applications, now)
  const window = replyWindow(applications)
  const rejected = metrics.rejBefore + metrics.rejAfter
  return {
    submitted: metrics.submitted,
    reachedInterview: metrics.reachedIv,
    offers: metrics.offers,
    rejected,
    awaitingReply: metrics.noResp,
    needsAttention: stale.filter(({ bucket }) => bucket !== 'fresh').length,
    interviewRate: rate(metrics.reachedIv, metrics.submitted),
    offerRate: rate(metrics.offers, metrics.submitted),
    timing: timing(applications),
    replyWindow: window,
    pastReplyWindow: stale.filter(({ bucket }) => bucket === 'ghosted').length,
    sufficient: metrics.submitted >= MIN_ANALYTICS_SAMPLE,
  }
}

function isDeliveredEvent(event: EngagementThread['events'][number]): boolean {
  return event.direction === 'outbound' && DELIVERED_STATES.has(event.state)
}

function isDelivered(thread: EngagementThread): boolean {
  return DELIVERED_STATES.has(thread.state) || thread.events.some(isDeliveredEvent)
}

function firstDeliveredAt(thread: EngagementThread): number | null {
  const events = thread.events
    .filter(isDeliveredEvent)
    .map(({ date }) => timestamp(date))
    .filter((date): date is number => date !== null)
  if (events.length) return Math.min(...events)
  return DELIVERED_STATES.has(thread.state) ? timestamp(thread.sent_at) : null
}

function firstReplyAt(thread: EngagementThread): number | null {
  const replies = thread.events
    .filter(({ direction, kind }) => direction === 'inbound' && kind === 'reply')
    .map(({ date }) => timestamp(date))
    .filter((date): date is number => date !== null)
  return replies.length ? Math.min(...replies) : null
}

function isOptOut(thread: EngagementThread): boolean {
  return thread.state === 'opted_out' || thread.events.some(({ kind }) => kind === 'opt_out')
}

function hasUnknownDelivery(thread: EngagementThread): boolean {
  return UNKNOWN_DELIVERY_STATES.has(thread.state) || thread.events.some((event) => (
    event.direction === 'outbound' && UNKNOWN_DELIVERY_STATES.has(event.state)
  ))
}

function summarizeCohort(threads: EngagementThread[]): OutreachCohort {
  const delivered = threads.filter(isDelivered)
  const repliedThreads = delivered.filter((thread) => !isOptOut(thread) && firstReplyAt(thread) !== null).length
  return {
    sentThreads: delivered.length,
    repliedThreads,
    responseRate: rate(repliedThreads, delivered.length),
  }
}

export function outreachAnalytics(threads: EngagementThread[]): OutreachAnalytics {
  const delivered = threads.filter(isDelivered)
  const cold = summarizeCohort(threads.filter(({ kind }) => kind === 'cold'))
  const application = summarizeCohort(threads.filter(({ kind }) => kind === 'application'))
  const repliedThreads = delivered.filter((thread) => !isOptOut(thread) && firstReplyAt(thread) !== null).length
  const optOuts = delivered.filter(isOptOut).length
  const replyGaps = delivered.flatMap((thread) => {
    if (isOptOut(thread)) return []
    const sent = firstDeliveredAt(thread)
    const reply = firstReplyAt(thread)
    return sent !== null && reply !== null && reply >= sent
      ? [Math.round((reply - sent) / DAY)]
      : []
  })

  return {
    sentThreads: delivered.length,
    repliedThreads,
    responseRate: rate(repliedThreads, delivered.length),
    followupsSent: delivered.reduce(
      (count, thread) => count + thread.events.filter((event) => (
        event.kind === 'followup' && isDeliveredEvent(event)
      )).length,
      0,
    ),
    awaitingReply: delivered.length - repliedThreads - optOuts,
    optOuts,
    deliveryUnknown: threads.filter(hasUnknownDelivery).length,
    medianDaysToReply: median(replyGaps),
    cohorts: { cold, application },
    sufficient: delivered.length >= MIN_ANALYTICS_SAMPLE,
  }
}