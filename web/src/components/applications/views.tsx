import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { AlignJustify, ChevronDown, Layers, List, Mail, Table2 } from 'lucide-react'
import type { Application } from '@/lib/schema'
import { AppCard, TimelineRow } from './AppCard'
import { STATUS_ORDER, presentStatuses, statusColor, statusLabel } from './constants'

export type AppView = 'list' | 'compact' | 'table' | 'grouped'
const VIEW_KEY = 'jobscope-apps-view'

const VIEWS: { id: AppView; label: string; icon: ReactNode }[] = [
  { id: 'list', label: 'List', icon: <List size={14} /> },
  { id: 'compact', label: 'Compact', icon: <AlignJustify size={14} /> },
  { id: 'table', label: 'Table', icon: <Table2 size={14} /> },
  { id: 'grouped', label: 'Grouped', icon: <Layers size={14} /> },
]

const byActivity = (a: Application, b: Application) =>
  (b.updated || b.applied_at || '').localeCompare(a.updated || a.applied_at || '')

const day = (iso: string) => (iso || '').slice(0, 10)

function ViewSwitcher({ value, onChange }: { value: AppView; onChange: (v: AppView) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-[10px] border border-border bg-bg2 p-0.5">
      {VIEWS.map((v) => {
        const active = v.id === value
        return (
          <button
            key={v.id}
            type="button"
            onClick={() => onChange(v.id)}
            aria-pressed={active}
            title={v.label}
            className={`flex items-center gap-1.5 rounded-[8px] px-2.5 py-1 text-[12px] font-medium transition ${
              active ? 'bg-card text-fg shadow-[var(--shadow)]' : 'text-mute hover:text-fg'
            }`}
          >
            {v.icon}
            <span className="hidden sm:inline">{v.label}</span>
          </button>
        )
      })}
    </div>
  )
}

function ListView({ apps }: { apps: Application[] }) {
  const sorted = useMemo(() => [...apps].sort(byActivity), [apps])
  return (
    <div className="flex flex-col gap-2.5">
      {sorted.map((a) => (
        <AppCard key={a.job_id || `${a.company}-${a.title}`} app={a} />
      ))}
    </div>
  )
}

function CompactRow({ app, onOpen }: { app: Application; onOpen?: (id: string) => void }) {
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(false)
  const events = app.timeline ?? []
  const status = app.status || 'new'
  const date = day(app.updated || app.applied_at)
  const toggle = () => (events.length ? setOpen((o) => !o) : app.job_id && onOpen?.(app.job_id))

  return (
    <div className="overflow-hidden rounded-[9px] border border-border bg-card">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[12.5px] transition hover:bg-card-h"
      >
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ background: statusColor(status) }}
          title={statusLabel(status)}
        />
        <span className="min-w-0 max-w-[38%] shrink-0 truncate font-semibold text-fg">{app.company || '—'}</span>
        <span className="min-w-0 flex-1 truncate text-dim">{app.title || ''}</span>
        <span className="hidden shrink-0 text-[11px] text-mute sm:inline">{statusLabel(status)}</span>
        {date && <time className="shrink-0 text-[11px] text-mute tnum">{date}</time>}
        {events.length > 0 && (
          <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-mute tnum">
            <Mail size={11} />
            {events.length}
          </span>
        )}
        {events.length > 0 && (
          <ChevronDown
            size={12}
            className="shrink-0 text-mute transition-transform"
            style={{ transform: open ? 'rotate(180deg)' : 'none' }}
          />
        )}
      </button>
      <AnimatePresence initial={false}>
        {open && events.length > 0 && (
          <motion.ul
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col gap-1.5 overflow-hidden border-t border-border px-3 py-2"
          >
            {events.map((e, i) => (
              <TimelineRow key={`${e.date}-${e.signal}-${i}`} e={e} />
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}

function CompactList({ apps, onOpen }: { apps: Application[]; onOpen?: (id: string) => void }) {
  const sorted = useMemo(() => [...apps].sort(byActivity), [apps])
  return (
    <div className="flex flex-col gap-1.5">
      {sorted.map((a) => (
        <CompactRow key={a.job_id || `${a.company}-${a.title}`} app={a} onOpen={onOpen} />
      ))}
    </div>
  )
}

type SortKey = 'company' | 'title' | 'status' | 'applied' | 'activity' | 'emails'

function AppTable({ apps }: { apps: Application[] }) {
  const [key, setKey] = useState<SortKey>('activity')
  const [dir, setDir] = useState<1 | -1>(-1)

  const rows = useMemo(() => {
    const val = (a: Application): string | number => {
      switch (key) {
        case 'company':
          return (a.company || '').toLowerCase()
        case 'title':
          return (a.title || '').toLowerCase()
        case 'status':
          return STATUS_ORDER.indexOf((a.status || 'new') as (typeof STATUS_ORDER)[number])
        case 'applied':
          return a.applied_at || ''
        case 'emails':
          return (a.timeline ?? []).length
        default:
          return a.updated || a.applied_at || ''
      }
    }
    return [...apps].sort((a, b) => {
      const va = val(a)
      const vb = val(b)
      if (va < vb) return -dir
      if (va > vb) return dir
      return 0
    })
  }, [apps, key, dir])

  const sortBy = (k: SortKey) => {
    if (k === key) setDir((d) => (d === 1 ? -1 : 1))
    else {
      setKey(k)
      setDir(k === 'company' || k === 'title' ? 1 : -1)
    }
  }
  const arrow = (k: SortKey) => (key === k ? (dir > 0 ? ' ↑' : ' ↓') : '')
  const thCls = 'cursor-pointer select-none px-3 py-2 font-semibold text-mute hover:text-fg'

  return (
    <div className="overflow-x-auto rounded-[12px] border border-border">
      <table className="w-full border-collapse text-left text-[12.5px]">
        <thead className="border-b border-border bg-bg2 text-[11px] uppercase tracking-wide">
          <tr>
            <th className={thCls} onClick={() => sortBy('company')}>Company{arrow('company')}</th>
            <th className={thCls} onClick={() => sortBy('title')}>Role{arrow('title')}</th>
            <th className={thCls} onClick={() => sortBy('status')}>Status{arrow('status')}</th>
            <th className={`${thCls} text-right`} onClick={() => sortBy('applied')}>Applied{arrow('applied')}</th>
            <th className={`${thCls} text-right`} onClick={() => sortBy('activity')}>Last activity{arrow('activity')}</th>
            <th className={`${thCls} text-right`} onClick={() => sortBy('emails')}>✉{arrow('emails')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const status = a.status || 'new'
            const color = statusColor(status)
            return (
              <tr key={a.job_id || `${a.company}-${a.title}`} className="border-b border-border/60 last:border-0 hover:bg-card-h">
                <td className="max-w-[14rem] truncate px-3 py-2 font-semibold text-fg">{a.company || '—'}</td>
                <td className="max-w-[18rem] truncate px-3 py-2 text-dim">{a.title || '—'}</td>
                <td className="px-3 py-2">
                  <span
                    className="rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize"
                    style={{ color, background: `color-mix(in srgb, ${color} 16%, transparent)` }}
                  >
                    {statusLabel(status)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-mute tnum">{day(a.applied_at) || '—'}</td>
                <td className="px-3 py-2 text-right text-mute tnum">{day(a.updated || a.applied_at) || '—'}</td>
                <td className="px-3 py-2 text-right text-mute tnum">{(a.timeline ?? []).length || ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function GroupedList({ apps }: { apps: Application[] }) {
  const groups = useMemo(
    () =>
      presentStatuses(apps).map((status) => ({
        status,
        label: statusLabel(status),
        color: statusColor(status),
        apps: apps.filter((a) => (a.status || 'new') === status).sort(byActivity),
      })),
    [apps],
  )
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set())
  const toggle = (s: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })

  return (
    <div className="flex flex-col gap-3">
      {groups.map((g) => {
        const isOpen = !collapsed.has(g.status)
        return (
          <section key={g.status} className="flex flex-col gap-2.5">
            <button
              type="button"
              onClick={() => toggle(g.status)}
              aria-expanded={isOpen}
              className="flex items-center gap-2 text-[13px] font-semibold"
            >
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: g.color }} />
              {g.label}
              <span className="text-dim tnum">{g.apps.length}</span>
              <ChevronDown
                size={14}
                className="text-mute transition-transform"
                style={{ transform: isOpen ? 'none' : 'rotate(-90deg)' }}
              />
            </button>
            {isOpen && (
              <div className="flex flex-col gap-2.5">
                {g.apps.map((a) => (
                  <AppCard key={a.job_id || `${a.company}-${a.title}`} app={a} />
                ))}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}

/** The applications board with a persisted List / Compact / Table / Grouped view switcher. */
export function ApplicationsSection({ apps, onOpen }: { apps: Application[]; onOpen?: (id: string) => void }) {
  const [view, setView] = useState<AppView>(() => {
    try {
      const v = localStorage.getItem(VIEW_KEY)
      return v === 'compact' || v === 'table' || v === 'grouped' ? v : 'list'
    } catch {
      return 'list'
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(VIEW_KEY, view)
    } catch {
      /* ignore */
    }
  }, [view])

  return (
    <section aria-label="All applications" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">
          All applications <span className="text-mute tnum">{apps.length}</span>
        </h3>
        <ViewSwitcher value={view} onChange={setView} />
      </div>
      {view === 'list' ? (
        <ListView apps={apps} />
      ) : view === 'compact' ? (
        <CompactList apps={apps} onOpen={onOpen} />
      ) : view === 'table' ? (
        <AppTable apps={apps} />
      ) : (
        <GroupedList apps={apps} />
      )}
    </section>
  )
}
