import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import type { Application } from '@/lib/schema'
import { CountUp } from '@/components/overview/CountUp'
import { AppCard } from './AppCard'
import { PipelineFlow } from './PipelineFlow'
import { pct, pipelineMetrics, presentStatuses, statusColor, statusCounts, statusLabel } from './constants'

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="js-gradient-card rounded-[14px] border border-border bg-card p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <span className="text-xs text-mute">{subtitle}</span>}
      </div>
      {children}
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

function KanbanBoard({ apps }: { apps: Application[] }) {
  const columns = useMemo(() => {
    return presentStatuses(apps).map((status) => ({
      status,
      label: statusLabel(status),
      color: statusColor(status),
      cards: apps
        .filter((a) => (a.status || 'new') === status)
        .sort((a, b) => (b.updated || '').localeCompare(a.updated || '')),
    }))
  }, [apps])

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3.5">
      {columns.map((col) => (
        <section
          key={col.status}
          aria-label={`${col.label} (${col.cards.length})`}
          className="js-gradient-column flex flex-col gap-2.5 self-start rounded-[14px] border border-border bg-bg2 p-3"
        >
          <h4 className="flex items-center gap-2 text-[13px] font-semibold">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: col.color }} />
            {col.label}
            <span className="ml-auto text-dim tnum">{col.cards.length}</span>
          </h4>
          {col.cards.map((a) => (
            <AppCard key={a.job_id || `${a.company}-${a.title}`} app={a} />
          ))}
        </section>
      ))}
    </div>
  )
}

export function Applications({ apps }: { apps: Application[] }) {
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

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card title="Application funnel" subtitle="by status">
          <StatusFunnel apps={apps} />
        </Card>
        <Card title="Pipeline flow" subtitle="how far each application got">
          {pipelineMetrics(apps).submitted > 0 ? (
            <PipelineFlow apps={apps} />
          ) : (
            <div className="grid min-h-28 place-items-center text-center text-[13px] text-mute">
              Nothing submitted yet — the flow appears once roles reach the applied stage.
            </div>
          )}
        </Card>
      </div>

      <KanbanBoard apps={apps} />
    </div>
  )
}
