import { ArrowRight } from 'lucide-react'
import { PipelineFlow } from '@/features/home'
import { pct, pipelineMetrics } from '@/components/applications/constants'
import type { Application } from '@/lib/schema'

export function PipelinePreview({ applications, onOpenAnalytics }: { applications: Application[]; onOpenAnalytics: () => void }) {
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
          onClick={onOpenAnalytics}
          className="mt-5 inline-flex items-center gap-2 text-[13px] font-semibold text-brand hover:underline"
        >
          Open analytics <ArrowRight size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

