import { useMemo } from 'react'
import type { Application } from '@/lib/schema'
import { signalColor, statusColor, statusLabel } from './constants'

interface FeedItem {
  key: string
  date: string
  signal: string
  subject: string
  from: string
  company: string
  title: string
  jobId: string
  status: string
}

/** Days between two YYYY-MM-DD strings (a - b), or null if either is unparseable. */
function daysBetween(a: string, b: string): number | null {
  const ta = Date.parse(a)
  const tb = Date.parse(b)
  if (Number.isNaN(ta) || Number.isNaN(tb)) return null
  return Math.round((ta - tb) / 86_400_000)
}

function relative(date: string, anchor: string): string {
  const d = daysBetween(anchor, date)
  if (d === null) return date
  if (d <= 0) return 'today'
  if (d === 1) return 'yesterday'
  if (d < 7) return `${d}d ago`
  if (d < 30) return `${Math.floor(d / 7)}w ago`
  return `${Math.floor(d / 30)}mo ago`
}

/**
 * Cross-application activity timeline: every email event across all tracked
 * applications, newest first — "what moved this week". Reads the same
 * `application.timeline[]` the drawer uses, so it needs no new data.
 */
export function ActivityFeed({ apps, onOpen }: { apps: Application[]; onOpen?: (id: string) => void }) {
  const { items, thisWeek } = useMemo(() => {
    const flat: FeedItem[] = []
    for (const a of apps) {
      for (let i = 0; i < (a.timeline ?? []).length; i++) {
        const e = a.timeline[i]
        if (!e.date && !e.subject) continue
        flat.push({
          key: `${a.job_id || a.company}-${i}`,
          date: e.date,
          signal: e.signal || 'other',
          subject: e.subject,
          from: e.from,
          company: a.company,
          title: a.title,
          jobId: a.job_id,
          status: a.status || 'new',
        })
      }
    }
    flat.sort((x, y) => (y.date || '').localeCompare(x.date || ''))
    const anchor = flat[0]?.date || ''
    const recent = flat.filter((f) => {
      const d = anchor ? daysBetween(anchor, f.date) : null
      return d !== null && d <= 7
    }).length
    return { items: flat, thisWeek: recent }
  }, [apps])

  if (items.length === 0) {
    return (
      <div className="grid min-h-28 place-items-center text-center text-[13px] text-mute">
        No email activity yet — replies land here as your applications progress.
      </div>
    )
  }

  const anchor = items[0].date

  return (
    <div>
      <div className="mb-3 text-[12.5px] text-mute">
        <span className="tnum text-fg">{thisWeek}</span> event{thisWeek === 1 ? '' : 's'} in the last 7 days
        {' · '}
        <span className="tnum text-fg">{items.length}</span> total
      </div>
      <ol className="relative max-h-[420px] overflow-auto pl-5">
        <span
          aria-hidden="true"
          className="absolute bottom-2 left-[6px] top-2 w-px bg-border"
        />
        {items.map((it) => {
          const clickable = Boolean(onOpen && it.jobId)
          return (
            <li key={it.key} className="relative pb-4 last:pb-0">
              <span
                aria-hidden="true"
                className="absolute -left-5 top-[5px] grid h-3 w-3 place-items-center"
              >
                <span
                  className="h-2.5 w-2.5 rounded-full ring-2 ring-card"
                  style={{ background: signalColor(it.signal) }}
                />
              </span>
              <button
                type="button"
                disabled={!clickable}
                onClick={() => clickable && onOpen?.(it.jobId)}
                className={
                  'group grid w-full grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 rounded-[9px] px-2 py-1.5 text-left transition ' +
                  (clickable ? 'cursor-pointer hover:bg-card-h' : 'cursor-default')
                }
              >
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className="min-w-0 truncate text-[13px] font-semibold text-fg">{it.company || '—'}</span>
                  <span
                    className="shrink-0 rounded-[5px] border px-1.5 font-mono text-[10px] font-bold capitalize leading-[1.4]"
                    style={{
                      color: signalColor(it.signal),
                      borderColor: `color-mix(in srgb, ${signalColor(it.signal)} 40%, transparent)`,
                    }}
                  >
                    {it.signal}
                  </span>
                </span>
                <time className="shrink-0 text-[11px] text-mute tnum" title={it.date}>
                  {relative(it.date, anchor)}
                </time>
                <span className="col-span-2 mt-0.5 flex min-w-0 items-baseline gap-2">
                  <span className="min-w-0 truncate text-[12px] text-dim" title={it.subject}>
                    {it.subject || it.title || '—'}
                  </span>
                  <span
                    className="shrink-0 text-[10.5px] font-medium tnum"
                    style={{ color: statusColor(it.status) }}
                  >
                    {statusLabel(it.status)}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
