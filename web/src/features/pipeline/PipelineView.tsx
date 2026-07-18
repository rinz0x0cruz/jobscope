import { ArrowRight, Clock3, Mail } from 'lucide-react'
import { useMemo, useState } from 'react'
import { PipelineFlow } from '@/features/home'
import { pct, pipelineMetrics, statusColor, statusLabel } from '@/components/applications/constants'
import type { Application } from '@/lib/schema'

type PipelineFilter = 'all' | 'applied' | 'interview' | 'offer' | 'rejected' | 'no-response'

export interface PipelineViewProps {
  applications: Application[]
  onOpen: (jobId: string) => void
}

const RESPONSE_SIGNALS = new Set(['recruiter', 'assessment', 'interview', 'offer', 'rejection'])

function noResponse(application: Application): boolean {
  return application.status === 'applied' && !(application.timeline ?? []).some((event) => RESPONSE_SIGNALS.has(event.signal))
}

function matches(application: Application, filter: PipelineFilter): boolean {
  if (filter === 'all') return ['applied', 'interview', 'offer', 'rejected'].includes(application.status)
  if (filter === 'no-response') return noResponse(application)
  return application.status === filter
}

function shortDate(value: string): string {
  if (!value) return '—'
  const time = Date.parse(value)
  if (Number.isNaN(time)) return value.slice(0, 10)
  return new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function PipelinePreview({ applications, onOpenPipeline }: { applications: Application[]; onOpenPipeline: () => void }) {
  const metrics = pipelineMetrics(applications)
  const waitingShare = pct(metrics.noResp, metrics.submitted)
  return (
    <div className="flex h-full min-h-0 flex-col bg-panel">
      <div className="border-b border-line px-6 py-5">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-3">Application pipeline</p>
        <h2 className="mt-1 text-lg font-semibold text-ink">Select a role to inspect it</h2>
        <p className="mt-1 text-[13px] text-ink-3">The pipeline remains visible until you choose a feed result.</p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-5 py-5">
        <PipelineFlow apps={applications} />
        <dl className="mt-5 grid grid-cols-3 border-y border-line text-center">
          <div className="py-3"><dt className="text-[10px] uppercase text-ink-3">Applied</dt><dd className="mt-1 font-mono text-lg text-ink">{metrics.submitted}</dd></div>
          <div className="border-x border-line py-3"><dt className="text-[10px] uppercase text-ink-3">Interview</dt><dd className="mt-1 font-mono text-lg text-ink">{metrics.reachedIv}</dd></div>
          <div className="py-3"><dt className="text-[10px] uppercase text-ink-3">Offer</dt><dd className="mt-1 font-mono text-lg text-ink">{metrics.offers}</dd></div>
        </dl>
        {metrics.submitted > 0 && (
          <div className="mt-5 border-b border-line pb-5">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-[10px] font-semibold uppercase text-ink-3">Awaiting response</p>
                <p className="mt-1 text-[13px] text-ink-2">Applications with no recorded recruiter outcome</p>
              </div>
              <strong className="font-mono text-2xl font-semibold text-ink">{metrics.noResp}</strong>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-inset">
              <div className="h-full rounded-full bg-ink-3" style={{ width: `${waitingShare}%` }} />
            </div>
            <p className="mt-1.5 text-right text-[11px] text-ink-3">{waitingShare}% of tracked applications</p>
          </div>
        )}
        <button
          type="button"
          onClick={onOpenPipeline}
          className="mt-5 inline-flex items-center gap-2 text-[13px] font-semibold text-brand hover:underline"
        >
          Open full pipeline <ArrowRight size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}




export function PipelineView({ applications, onOpen }: PipelineViewProps) {
  const [filter, setFilter] = useState<PipelineFilter>('all')
  const relevant = useMemo(
    () => applications.filter((application) => matches(application, filter)),
    [applications, filter],
  )
  const controls: Array<{ value: PipelineFilter; label: string; count: number }> = [
    { value: 'all', label: 'All', count: applications.filter((application) => matches(application, 'all')).length },
    { value: 'applied', label: 'Applied', count: applications.filter((application) => matches(application, 'applied')).length },
    { value: 'interview', label: 'Interview', count: applications.filter((application) => matches(application, 'interview')).length },
    { value: 'offer', label: 'Offer', count: applications.filter((application) => matches(application, 'offer')).length },
    { value: 'rejected', label: 'Rejected', count: applications.filter((application) => matches(application, 'rejected')).length },
    { value: 'no-response', label: 'No response', count: applications.filter(noResponse).length },
  ]

  return (
    <div className="mx-auto max-w-7xl border-x border-line bg-panel">
      <header className="border-b border-line px-5 py-5 sm:px-7">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-3">Pipeline</p>
        <h2 className="mt-1 text-xl font-semibold text-ink">How applications progress</h2>
        <p className="mt-1 text-[13px] text-ink-3">Inspect conversion, then narrow the application register by outcome.</p>
      </header>
      <section className="border-b border-line px-4 py-5 sm:px-7" aria-label="Pipeline graph">
        <PipelineFlow apps={applications} />
      </section>
      <div className="flex items-center gap-2 overflow-x-auto border-b border-line px-4 py-2.5 sm:px-7">
        {controls.map((control) => (
          <button
            key={control.value}
            type="button"
            onClick={() => setFilter(control.value)}
            aria-pressed={filter === control.value}
            className={`h-8 shrink-0 rounded-full border px-3 text-[11px] font-medium transition ${
              filter === control.value
                ? 'border-brand bg-brand-weak text-brand'
                : 'border-line text-ink-2 hover:border-line-strong'
            }`}
          >
            {control.label} · {control.count}
          </button>
        ))}
      </div>
      <section aria-label="Pipeline applications">
        {relevant.length ? (
          <ul>
            {relevant.map((application) => (
              <li key={application.job_id} className="border-b border-line last:border-b-0">
                <button
                  type="button"
                  onClick={() => onOpen(application.job_id)}
                  aria-label={`${application.company} — ${application.title || 'Application'}`}
                  className="grid w-full gap-2 px-5 py-3 text-left outline-none transition hover:bg-inset/60 focus-visible:bg-inset sm:grid-cols-[minmax(0,1.3fr)_8rem_7rem_minmax(8rem,.65fr)] sm:items-center sm:px-7"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[14px] font-semibold text-ink">{application.title || 'Application'}</span>
                    <span className="block truncate text-[12px] text-ink-3">{application.company}</span>
                  </span>
                  <span className="text-[12px] font-medium" style={{ color: statusColor(application.status) }}>
                    {statusLabel(application.status)}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-ink-3">
                    <Clock3 size={11} aria-hidden="true" />{shortDate(application.updated || application.applied_at)}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-ink-3">
                    <Mail size={11} aria-hidden="true" />{application.timeline.length} update{application.timeline.length === 1 ? '' : 's'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-6 py-12 text-center text-[13px] text-ink-3">No applications in this stage.</p>
        )}
      </section>
    </div>
  )
}

