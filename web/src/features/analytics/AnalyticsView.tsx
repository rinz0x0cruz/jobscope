import { Clock3, MailCheck, MessageSquareReply } from 'lucide-react'
import { PipelineFlow } from '@/features/home'
import {
  MIN_ANALYTICS_SAMPLE,
  applicationAnalytics,
  outreachAnalytics,
  type RateMetric,
} from '@/lib/analytics'
import type { EngagementThread } from '@/lib/campaigns'
import type { Application } from '@/lib/schema'
import { Segmented, WorkspaceHeader } from '@/ui'

export type AnalyticsMode = 'applications' | 'outreach'

export interface AnalyticsViewProps {
  mode: AnalyticsMode
  onModeChange: (mode: AnalyticsMode) => void
  applications: Application[]
  engagements: EngagementThread[]
  outreachAvailable: boolean
}

function Evidence({ sufficient, sample }: { sufficient: boolean; sample: string }) {
  return (
    <span className={`text-[11px] ${sufficient ? 'text-ink-3' : 'font-medium text-stretch'}`}>
      {sufficient ? sample : `Insufficient evidence · ${sample}`}
    </span>
  )
}

function RateStat({
  label,
  rate,
  sufficient,
  sample,
}: {
  label: string
  rate: RateMetric
  sufficient: boolean
  sample: string
}) {
  return (
    <div className="min-w-0 border-l-2 border-transparent px-4 py-4 first:border-l-brand sm:px-5">
      <dt className="text-[11px] font-semibold text-ink-3">{label}</dt>
      <dd className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <strong className="font-mono text-2xl font-semibold text-ink">
          {sufficient ? `${rate.percent}%` : '—'}
        </strong>
        <span className="font-mono text-[12px] text-ink-2">{rate.numerator} / {rate.denominator}</span>
      </dd>
      <Evidence sufficient={sufficient} sample={sample} />
    </div>
  )
}

function CountStat({ label, value, detail }: { label: string; value: number | string; detail: string }) {
  return (
    <div className="min-w-0 px-4 py-4 sm:px-5">
      <dt className="text-[11px] font-semibold text-ink-3">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-semibold text-ink">{value}</dd>
      <span className="text-[11px] text-ink-3">{detail}</span>
    </div>
  )
}

function ApplicationAnalyticsView({ applications }: { applications: Application[] }) {
  const metrics = applicationAnalytics(applications)
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <section className="border-b border-line bg-paper px-4 py-5 sm:px-7" aria-labelledby="application-funnel-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 id="application-funnel-heading" className="text-[14px] font-semibold text-ink">Application pipeline</h3>
            <p className="mt-1 text-[12px] text-ink-3">How submitted roles progressed, without mixing in outreach activity.</p>
          </div>
          <Evidence sufficient={metrics.sufficient} sample={`${metrics.submitted} submitted applications`} />
        </div>
        <PipelineFlow apps={applications} />
      </section>

      <dl className="grid border-b border-line bg-panel sm:grid-cols-2 min-[1200px]:grid-cols-4 [&>*]:border-b [&>*]:border-line sm:[&>*]:border-r min-[1200px]:[&>*]:border-b-0">
        <RateStat label="Reached interview" rate={metrics.interviewRate} sufficient={metrics.sufficient} sample={`${metrics.submitted} submitted applications`} />
        <RateStat label="Reached offer" rate={metrics.offerRate} sufficient={metrics.sufficient} sample={`${metrics.submitted} submitted applications`} />
        <CountStat label="Awaiting response" value={metrics.awaitingReply} detail={`${metrics.submitted} submitted`} />
        <CountStat label="Needs attention" value={metrics.needsAttention} detail="7+ days without a reply" />
      </dl>

      <section className="bg-inset/25 px-4 py-5 sm:px-7" aria-labelledby="application-timing-heading">
        <div className="flex items-center gap-2">
          <Clock3 size={16} className="text-brand" aria-hidden="true" />
          <h3 id="application-timing-heading" className="text-[14px] font-semibold text-ink">Response timing</h3>
        </div>
        <dl className="mt-4 grid border-y border-line sm:grid-cols-3 [&>*]:border-b [&>*]:border-line sm:[&>*]:border-b-0 sm:[&>*]:border-r sm:[&>*:last-child]:border-r-0">
          <TimingStat
            label="Median first reply"
            days={metrics.timing.medianDaysToReply}
            sample={metrics.timing.replied}
            unit="application"
          />
          <TimingStat
            label="Median to interview"
            days={metrics.timing.medianDaysToInterview}
            sample={metrics.timing.interviewed}
            unit="application"
          />
          <CountStat label="Rejected" value={metrics.rejected} detail={`${metrics.submitted} submitted`} />
        </dl>
      </section>
    </div>
  )
}

function OutreachAnalyticsView({ engagements, available }: { engagements: EngagementThread[]; available: boolean }) {
  if (!available) {
    return (
      <div className="grid min-h-64 place-items-center px-6 text-center">
        <div className="max-w-md">
          <MailCheck size={22} className="mx-auto text-ink-3" aria-hidden="true" />
          <h3 className="mt-3 text-[14px] font-semibold text-ink">Outreach analytics unavailable</h3>
          <p className="mt-1 text-[12px] text-ink-3">Open the private local workspace to read engagement history.</p>
        </div>
      </div>
    )
  }

  const metrics = outreachAnalytics(engagements)
  const cohorts = [
    { label: 'Cold outreach', value: metrics.cohorts.cold },
    { label: 'Application follow-ups', value: metrics.cohorts.application },
  ]
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <section className="border-b border-line bg-paper px-4 py-5 sm:px-7" aria-labelledby="outreach-response-heading">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 id="outreach-response-heading" className="text-[14px] font-semibold text-ink">Thread outcomes</h3>
            <p className="mt-1 text-[12px] text-ink-3">Each root conversation counts once, even when follow-ups were sent.</p>
          </div>
          <Evidence sufficient={metrics.sufficient} sample={`${metrics.sentThreads} sent threads`} />
        </div>
        <dl className="grid border-y border-line bg-panel sm:grid-cols-2 min-[1200px]:grid-cols-4 [&>*]:border-b [&>*]:border-line sm:[&>*]:border-r min-[1200px]:[&>*]:border-b-0">
          <RateStat label="Response rate" rate={metrics.responseRate} sufficient={metrics.sufficient} sample={`${metrics.sentThreads} sent threads`} />
          <CountStat label="Replied threads" value={metrics.repliedThreads} detail={`${metrics.sentThreads} sent threads`} />
          <CountStat label="Awaiting reply" value={metrics.awaitingReply} detail={`${metrics.sentThreads} sent threads`} />
          <TimingStat
            label="Median reply time"
            days={metrics.medianDaysToReply}
            sample={metrics.repliedThreads}
            unit="thread"
          />
        </dl>
      </section>

      <dl className="grid border-b border-line bg-inset/25 sm:grid-cols-2 min-[1200px]:grid-cols-4 [&>*]:border-b [&>*]:border-line sm:[&>*]:border-r min-[1200px]:[&>*]:border-b-0">
        <CountStat label="Sent threads" value={metrics.sentThreads} detail="Unique root conversations" />
        <CountStat label="Follow-ups sent" value={metrics.followupsSent} detail="Excluded from response denominator" />
        <CountStat label="Opt-outs" value={metrics.optOuts} detail={`${metrics.sentThreads} sent threads`} />
        <CountStat label="Delivery unknown" value={metrics.deliveryUnknown} detail="Requires manual Sent-folder check" />
      </dl>

      <section className="px-4 py-5 sm:px-7" aria-labelledby="outreach-cohorts-heading">
        <div className="flex items-center gap-2">
          <MessageSquareReply size={16} className="text-brand" aria-hidden="true" />
          <h3 id="outreach-cohorts-heading" className="text-[14px] font-semibold text-ink">Outreach cohorts</h3>
        </div>
        <div className="mt-4 border-y border-line">
          {cohorts.map(({ label, value }) => {
            const sufficient = value.sentThreads >= MIN_ANALYTICS_SAMPLE
            return (
              <div key={label} className="grid gap-2 border-b border-line px-4 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
                <div>
                  <h4 className="text-[13px] font-semibold text-ink">{label}</h4>
                  <Evidence sufficient={sufficient} sample={`${value.sentThreads} sent threads`} />
                </div>
                <span className="font-mono text-[12px] text-ink-2">{value.repliedThreads} replied / {value.sentThreads} sent</span>
                <strong className="w-16 text-left font-mono text-lg text-ink sm:text-right">
                  {sufficient ? `${value.responseRate.percent}%` : '—'}
                </strong>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}

export function AnalyticsView({
  mode,
  onModeChange,
  applications,
  engagements,
  outreachAvailable,
}: AnalyticsViewProps) {
  return (
    <section className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col border-x border-line bg-panel">
      <WorkspaceHeader
        eyebrow="Evidence"
        title="Analytics"
        description="Compare outcomes and timing without mixing application and outreach denominators."
        actions={<Segmented
          ariaLabel="Analytics mode"
          value={mode}
          onChange={(value) => onModeChange(value as AnalyticsMode)}
          options={[
            { value: 'applications', label: 'Applications' },
            { value: 'outreach', label: 'Outreach' },
          ]}
        />}
        accent="signal"
      />
      {mode === 'applications' ? (
        <ApplicationAnalyticsView applications={applications} />
      ) : (
        <OutreachAnalyticsView engagements={engagements} available={outreachAvailable} />
      )}
    </section>
  )
}

function TimingStat({
  label,
  days,
  sample,
  unit,
}: {
  label: string
  days: number | null
  sample: number
  unit: 'application' | 'thread'
}) {
  const sufficient = sample >= MIN_ANALYTICS_SAMPLE
  return (
    <div className="min-w-0 px-4 py-4 sm:px-5">
      <dt className="text-[11px] font-semibold text-ink-3">{label}</dt>
      <dd className="mt-1 font-mono text-2xl font-semibold text-ink">
        {sufficient && days !== null ? `${days}d` : '—'}
      </dd>
      <Evidence sufficient={sufficient} sample={`${sample} measured ${sample === 1 ? unit : `${unit}s`}`} />
    </div>
  )
}