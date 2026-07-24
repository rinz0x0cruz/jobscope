import { describe, expect, it } from 'vitest'
import { applicationAnalytics, outreachAnalytics } from '@/lib/analytics'
import type { EngagementThread } from '@/lib/campaigns'
import { application } from './factories'

const NOW = Date.parse('2026-07-23T00:00:00Z')
const event = (date: string, signal: string) => ({ date, signal, subject: '', from: '', summary: '' })

function engagement(over: Partial<EngagementThread> = {}): EngagementThread {
  return {
    id: 'cold:one', kind: 'cold', application_job_id: '', company: 'Acme', title: '',
    campaign_id: 'campaign:one', target_id: 'target:one', recipient: 'r@acme.test',
    subject: 'Hello', state: 'sent', sent_at: '2026-07-10T00:00:00Z',
    latest_activity_at: '2026-07-10T00:00:00Z', followup_count: 0,
    outbound_count: 1, reply_count: 0,
    events: [{
      direction: 'outbound', kind: 'cold', date: '2026-07-10T00:00:00Z',
      subject: 'Hello', participant: 'r@acme.test', summary: '', state: 'sent',
      signal: '', followup_number: 0, campaign_id: 'campaign:one', target_id: 'target:one',
    }],
    ...over,
  }
}

describe('application analytics', () => {
  it('uses explicit application samples for conversion and timing', () => {
    const result = applicationAnalytics([
      application({ job_id: 'awaiting', applied_at: '2026-07-10T00:00:00Z' }),
      application({ job_id: 'interview', status: 'interview', applied_at: '2026-07-01T00:00:00Z', timeline: [event('2026-07-05T00:00:00Z', 'interview')] }),
      application({ job_id: 'offer', status: 'offer', applied_at: '2026-07-02T00:00:00Z', timeline: [event('2026-07-06T00:00:00Z', 'recruiter'), event('2026-07-08T00:00:00Z', 'interview')] }),
      application({ job_id: 'rejected', status: 'rejected', applied_at: '2026-07-03T00:00:00Z' }),
    ], NOW)

    expect(result.submitted).toBe(4)
    expect(result.reachedInterview).toBe(2)
    expect(result.offers).toBe(1)
    expect(result.rejected).toBe(1)
    expect(result.awaitingReply).toBe(1)
    expect(result.needsAttention).toBe(1)
    expect(result.interviewRate).toEqual({ numerator: 2, denominator: 4, percent: 50 })
    expect(result.timing.medianDaysToReply).toBe(4)
    expect(result.sufficient).toBe(true)
  })

  it('marks small samples as insufficient evidence', () => {
    expect(applicationAnalytics([application({ job_id: 'one' })], NOW).sufficient).toBe(false)
  })
})

describe('outreach analytics', () => {
  it('counts root threads, not messages, and excludes unknown delivery attempts', () => {
    const result = outreachAnalytics([
      engagement({
        id: 'cold:replied', followup_count: 1, outbound_count: 2, reply_count: 1,
        latest_activity_at: '2026-07-12T00:00:00Z', state: 'replied',
        events: [
          engagement().events[0],
          { ...engagement().events[0], kind: 'followup', date: '2026-07-11T00:00:00Z', followup_number: 1 },
          { direction: 'inbound', kind: 'reply', date: '2026-07-12T00:00:00Z', subject: 'Re: Hello', participant: 'r@acme.test', summary: '', state: 'replied', signal: 'campaign_reply', followup_number: 1, campaign_id: 'campaign:one', target_id: 'target:one' },
        ],
      }),
      engagement({ id: 'application:awaiting', kind: 'application', application_job_id: 'job:one', campaign_id: '', target_id: '', state: 'sent' }),
      engagement({
        id: 'cold:optout', state: 'opted_out', reply_count: 1,
        events: [
          engagement().events[0],
          { direction: 'inbound', kind: 'opt_out', date: '2026-07-11T00:00:00Z', subject: 'Remove me', participant: 'r@acme.test', summary: '', state: 'opted_out', signal: 'campaign_optout', followup_number: 0, campaign_id: 'campaign:one', target_id: 'target:one' },
        ],
      }),
      engagement({
        id: 'cold:unknown', state: 'delivery_unknown',
        events: [{ ...engagement().events[0], state: 'delivery_unknown' }],
      }),
    ])

    expect(result.sentThreads).toBe(3)
    expect(result.followupsSent).toBe(1)
    expect(result.repliedThreads).toBe(1)
    expect(result.awaitingReply).toBe(1)
    expect(result.optOuts).toBe(1)
    expect(result.deliveryUnknown).toBe(1)
    expect(result.responseRate).toEqual({ numerator: 1, denominator: 3, percent: 33 })
    expect(result.medianDaysToReply).toBe(2)
    expect(result.cohorts.cold.sentThreads).toBe(2)
    expect(result.cohorts.application.sentThreads).toBe(1)
    expect(result.sufficient).toBe(true)
  })

  it('returns empty, insufficient metrics without NaN percentages', () => {
    const result = outreachAnalytics([])
    expect(result.responseRate).toEqual({ numerator: 0, denominator: 0, percent: 0 })
    expect(result.medianDaysToReply).toBeNull()
    expect(result.sufficient).toBe(false)
  })

  it('keeps a delivered root when a follow-up is unknown and excludes sending-only roots', () => {
    const deliveredThenUnknown = engagement({
      id: 'cold:followup-unknown', state: 'delivery_unknown', followup_count: 1,
      outbound_count: 2,
      events: [
        engagement().events[0],
        {
          ...engagement().events[0], kind: 'followup', state: 'delivery_unknown',
          date: '2026-07-11T00:00:00Z', followup_number: 1,
        },
      ],
    })
    const sendingOnly = engagement({
      id: 'cold:sending', state: 'sending',
      events: [{ ...engagement().events[0], state: 'sending' }],
    })

    const result = outreachAnalytics([deliveredThenUnknown, sendingOnly])
    expect(result.sentThreads).toBe(1)
    expect(result.followupsSent).toBe(0)
    expect(result.awaitingReply).toBe(1)
    expect(result.deliveryUnknown).toBe(2)
  })
})