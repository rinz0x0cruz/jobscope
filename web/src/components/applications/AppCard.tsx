import { useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ChevronDown, Mail } from 'lucide-react'
import type { Application, ApplicationEvent } from '@/lib/schema'
import { trackSpotlight } from '@/lib/spotlight'
import type { CSSProperties } from 'react'
import { signalColor, statusColor, statusLabel } from './constants'

function TimelineRow({ e }: { e: ApplicationEvent }) {
  return (
    <li className="flex flex-col gap-1 text-[11.5px]">
      <div className="flex items-center gap-2">
        <span
          className="shrink-0 rounded-[5px] border px-1.5 font-mono text-[10px] font-bold capitalize leading-[1.35]"
          style={{
            color: signalColor(e.signal),
            borderColor: `color-mix(in srgb, ${signalColor(e.signal)} 40%, transparent)`,
          }}
        >
          {e.signal || 'other'}
        </span>
        <span className="min-w-0 flex-1 truncate text-dim" title={e.subject}>
          {e.subject || '\u2014'}
        </span>
        {e.from && <span className="shrink-0 truncate text-mute" title={e.from}>{e.from}</span>}
        {e.date && <time className="shrink-0 text-mute tnum">{e.date}</time>}
      </div>
      {e.summary && (
        <p className="line-clamp-3 pl-[3px] text-[11px] leading-relaxed text-mute">
          {e.summary}
        </p>
      )}
    </li>
  )
}

export function AppCard({ app }: { app: Application }) {
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(false)
  const events = app.timeline ?? []
  const date = (app.applied_at || app.updated || '').slice(0, 10)
  const status = app.status || 'new'
  const accent = statusColor(status)

  return (
    <article
      data-status={status}
      className="js-gradient-card js-spotlight-card js-status-card rounded-[10px] border border-border bg-card p-3 transition-colors hover:border-border-h hover:bg-card-h"
      onPointerMove={trackSpotlight}
      style={{ '--status-color': accent, '--spot-color': accent } as CSSProperties}
    >
      <span className="js-status-rail" aria-hidden="true" />
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{app.company || '—'}</span>
        <span
          className="shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-semibold capitalize leading-none"
          style={{ color: accent, background: `color-mix(in srgb, ${accent} 16%, transparent)` }}
        >
          {statusLabel(status)}
        </span>
        {date && <time className="shrink-0 text-[11px] text-mute tnum">{date}</time>}
      </div>
      {app.title && <div className="mt-0.5 truncate text-[12.5px] text-dim">{app.title}</div>}

      {(app.source || events.length > 0) && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {app.source && (
            <span className="rounded-md border border-border bg-bg2 px-1.5 py-0.5 text-[11px] text-dim">
              {app.source}
            </span>
          )}
          {events.length > 0 && (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              aria-label={`${open ? 'Hide' : 'Show'} ${events.length} email ${events.length === 1 ? 'event' : 'events'}`}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-bg2 px-1.5 py-0.5 text-[11px] text-dim outline-none transition-colors hover:border-border-h hover:text-fg focus-visible:border-accent"
            >
              <Mail size={11} />
              <span className="tnum">{events.length}</span>
              {events.length === 1 ? 'email' : 'emails'}
              <ChevronDown
                size={12}
                className="transition-transform"
                style={{ transform: open ? 'rotate(180deg)' : 'none' }}
              />
            </button>
          )}
        </div>
      )}

      <AnimatePresence initial={false}>
        {open && events.length > 0 && (
          <motion.ul
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="mt-2 flex flex-col gap-1.5 overflow-hidden border-t border-border pt-2"
          >
            {events.map((e, i) => (
              <TimelineRow key={`${e.date}-${e.signal}-${i}`} e={e} />
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </article>
  )
}
