import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import type { Application, EncBlob } from '@/lib/schema'
import { trackSpotlight } from '@/lib/spotlight'
import { CountUp } from '@/components/overview/CountUp'
import { AppCard } from './AppCard'
import { ActivityFeed } from './ActivityFeed'
import { ApplicationsGate, type UnlockedApps } from './ApplicationsGate'
import { PipelineFlow } from './PipelineFlow'
import { PipelineHealth } from './PipelineHealth'
import { pct, pipelineMetrics, statusCounts } from './constants'

function Card({ title, subtitle, children, className = '' }: { title: string; subtitle?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`js-gradient-card js-spotlight-card flex flex-col rounded-[14px] border border-border bg-card p-4 ${className}`} onPointerMove={trackSpotlight}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <span className="text-xs text-mute">{subtitle}</span>}
      </div>
      <div className="flex min-h-0 flex-1 flex-col justify-center">{children}</div>
    </section>
  )
}

/** Counts per status in canonical order, drawn as colored horizontal bars. */
function StatusFunnel({ apps }: { apps: Application[] }) {
  const reduce = useReducedMotion()
  const [on, setOn] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setOn(true), 40)
    return () => clearTimeout(id)
  }, [])
  const grown = reduce || on

  const rows = statusCounts(apps)
  if (rows.length === 0) return null
  const max = Math.max(1, ...rows.map((r) => r.count))

  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((r, i) => (
        <div key={r.status}>
          <div className="mb-1 flex items-center justify-between gap-2 text-[13px]">
            <span className="min-w-0 truncate text-fg">{r.label}</span>
            <span className="shrink-0 text-mute tnum">{r.count}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full"
              style={{
                background: r.color,
                width: grown ? `${(r.count / max) * 100}%` : '0%',
                transition: reduce ? 'none' : `width 0.6s ease-out ${i * 0.04}s`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function ApplicationList({ apps }: { apps: Application[] }) {
  const sorted = useMemo(
    () =>
      [...apps].sort((a, b) =>
        (b.updated || b.applied_at || '').localeCompare(a.updated || a.applied_at || ''),
      ),
    [apps],
  )

  return (
    <section aria-label="All applications" className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">All applications</h3>
        <span className="text-xs text-mute tnum">{apps.length}</span>
      </div>
      <div className="flex flex-col gap-2.5">
        {sorted.map((a) => (
          <AppCard key={a.job_id || `${a.company}-${a.title}`} app={a} />
        ))}
      </div>
    </section>
  )
}

export function Applications({
  apps,
  encBlob,
  onUnlock,
  onOpen,
}: {
  apps: Application[]
  encBlob?: EncBlob | null
  onUnlock?: (data: UnlockedApps) => void
  onOpen?: (id: string) => void
}) {
  const summary = useMemo(() => {
    const p = pipelineMetrics(apps)
    const responded = p.reachedIv + p.rejBefore
    return {
      total: apps.length,
      submitted: p.submitted,
      responseRate: pct(responded, p.submitted),
      interviewRate: pct(p.reachedIv, p.submitted),
      offers: p.offers,
    }
  }, [apps])

  if (apps.length === 0) {
    // No baked apps: this is a redacted/public build. If an encrypted blob was
    // shipped, offer the passphrase gate; otherwise show the empty state.
    if (encBlob && onUnlock) {
      return <ApplicationsGate blob={encBlob} onUnlock={onUnlock} />
    }
    return (
      <div className="grid min-h-40 place-items-center rounded-[14px] border border-border bg-card p-8 text-center text-[13px] text-mute">
        No applications tracked yet — mark roles as applied to build your funnel.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-mute">
        Tracking <span className="tnum text-fg"><CountUp value={summary.total} /></span> applications
        {summary.submitted > 0 && (
          <>
            {' · '}
            <span className="tnum text-fg">{summary.submitted}</span> submitted{' · '}
            <span className="tnum text-fg">{summary.responseRate}%</span> response{' · '}
            <span className="tnum text-fg">{summary.interviewRate}%</span> interview
            {summary.offers > 0 && (
              <>
                {' · '}
                <span className="tnum text-fg">{summary.offers}</span> offer
                {summary.offers === 1 ? '' : 's'}
              </>
            )}
          </>
        )}
      </p>

      <PipelineHealth apps={apps} onOpen={onOpen} />

      <div className="grid gap-4 md:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Card title="Pipeline flow" subtitle="how far each application progressed">
          {pipelineMetrics(apps).submitted > 0 ? (
            <PipelineFlow apps={apps} />
          ) : (
            <div className="grid min-h-28 flex-1 place-items-center text-center text-[13px] text-mute">
              Nothing submitted yet — the flow appears once roles reach the applied stage.
            </div>
          )}
        </Card>
        <Card title="By status" subtitle="applications per stage">
          <StatusFunnel apps={apps} />
        </Card>
      </div>

      <Card title="Recent activity" subtitle="latest email events across all applications">
        <ActivityFeed apps={apps} onOpen={onOpen} />
      </Card>

      <ApplicationList apps={apps} />
    </div>
  )
}
