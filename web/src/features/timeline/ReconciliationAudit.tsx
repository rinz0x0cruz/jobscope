import { CheckCircle2, RotateCcw, ShieldCheck, TriangleAlert } from 'lucide-react'
import type { ActivityAudit, RecoverableApplication } from '@/lib/schema'

export interface ReconciliationAuditProps {
  audit: ActivityAudit
  onRecover: (jobId: string) => void
}

function label(value: string): string {
  return value.replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase())
}

function runTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }).format(parsed)
}

function confirmRecovery(application: RecoverableApplication): boolean {
  const identity = application.title || application.company || application.job_id
  return window.confirm(
    `Restore ${identity}? The application will return to the active register and be marked ` +
      'reconciliation-exempt so the next recompute does not remove it again.',
  )
}

export function ReconciliationAudit({ audit, onRecover }: ReconciliationAuditProps) {
  const latest = audit.recent_runs[0]
  if (!latest && audit.recoverable_applications.length === 0) return null

  return (
    <section className="max-h-72 shrink-0 overflow-auto border-b border-line" aria-label="Reconciliation audit">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-inset px-5 py-3 sm:px-7">
        <div className="flex min-w-0 items-center gap-2.5">
          <ShieldCheck size={17} className="shrink-0 text-good" aria-hidden="true" />
          <div className="min-w-0">
            <h3 className="text-[12px] font-semibold text-ink">Reconciliation integrity</h3>
            {latest ? (
              <p className="mt-0.5 text-[11px] text-ink-3">
                {label(latest.action)} · {latest.applications_before} → {latest.applications_after ?? '?'} applications
                {latest.completed_at ? ` · ${runTime(latest.completed_at)}` : ''}
              </p>
            ) : (
              <p className="mt-0.5 text-[11px] text-ink-3">No reconciliation run recorded</p>
            )}
          </div>
        </div>
        {latest && (
          <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-ink-2">
            {latest.status === 'completed' ? (
              <CheckCircle2 size={14} className="text-good" aria-hidden="true" />
            ) : (
              <TriangleAlert size={14} className="text-stretch" aria-hidden="true" />
            )}
            {label(latest.status)}
          </span>
        )}
      </header>

      {latest && (
        <dl className="grid grid-cols-2 border-b border-line sm:grid-cols-4">
          {[
            ['Groups', latest.groups_count],
            ['Instances', latest.instances_count],
            ['Reclassified', latest.reclassified_count],
            ['Tombstoned', latest.tombstoned_count],
          ].map(([metric, value]) => (
            <div key={metric} className="border-r border-line px-5 py-2 last:border-r-0 sm:px-7">
              <dt className="text-[9px] font-semibold uppercase text-ink-3">{metric}</dt>
              <dd className="mt-0.5 font-mono text-[13px] font-semibold text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(320px,.72fr)]">
        <div className="border-b border-line lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between border-b border-line px-5 py-2 sm:px-7">
            <h4 className="text-[10px] font-semibold uppercase text-ink-3">Latest decisions</h4>
            <span className="font-mono text-[11px] text-ink-3">{audit.decisions.length}</span>
          </div>
          {audit.decisions.length ? (
            <ol>
              {audit.decisions.slice(0, 12).map((decision) => (
                <li key={decision.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-line px-5 py-2.5 last:border-b-0 sm:px-7">
                  <span className="min-w-0">
                    <span className="block truncate text-[12px] font-medium text-ink">{label(decision.decision_type)}</span>
                    <span className="mt-0.5 block text-[10px] text-ink-3">{label(decision.reason_code)}</span>
                  </span>
                  <span className="self-center font-mono text-[10px] text-ink-3">#{decision.sequence}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="px-5 py-5 text-[12px] text-ink-3 sm:px-7">No mutation decisions in the latest run.</p>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between border-b border-line px-5 py-2 sm:px-7">
            <h4 className="text-[10px] font-semibold uppercase text-ink-3">Recoverable</h4>
            <span className="font-mono text-[11px] text-ink-3">{audit.recoverable_applications.length}</span>
          </div>
          {audit.recoverable_applications.length ? (
            <ul>
              {audit.recoverable_applications.map((application) => (
                <li key={application.job_id} className="flex items-center gap-3 border-b border-line px-5 py-2.5 last:border-b-0 sm:px-7">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12px] font-medium text-ink">
                      {application.title || application.company || 'Application'}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] text-ink-3">
                      {application.company || application.status} · {label(application.tombstone_reason)}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (confirmRecovery(application)) onRecover(application.job_id)
                    }}
                    className="inline-flex h-8 shrink-0 items-center gap-1.5 border border-line px-2.5 text-[11px] font-semibold text-ink outline-none transition-colors hover:bg-inset focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    <RotateCcw size={13} aria-hidden="true" /> Restore
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-5 text-[12px] text-ink-3 sm:px-7">No recoverable applications.</p>
          )}
        </div>
      </div>
    </section>
  )
}