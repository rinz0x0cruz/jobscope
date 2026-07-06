import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, DownloadCloud, LayoutGrid, List, MailSearch, Search, Send, Star, SunMoon } from 'lucide-react'
import type { JobRow } from '@/lib/schema'
import { TIER_COLOR } from '@/lib/schema'
import type { TabValue } from '@/lib/urlState'
import { useTheme } from '@/hooks/useTheme'
import { pullLatestData, scanNewMail } from '@/lib/refresh'
import { fuzzy, makeFuse } from '@/lib/search'

/** Fired by the header command pill (in addition to ⌘K / "/") to open the palette. */
export const COMMAND_EVENT = 'jobscope:command'

const HEADING =
  '[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-bold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.18em] [&_[cmdk-group-heading]]:text-mute'

function isTyping(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
}

interface Action {
  id: string
  label: string
  hint?: string
  keywords: string
  icon: React.ReactNode
  run: () => void
}

interface Props {
  rows: JobRow[]
  onNavigate?: (tab: TabValue) => void
}

/** Ctrl/Cmd-K (or "/") command bar: jump between views, toggle the theme, or
 *  fuzzy-search every role. Also opens on a `jobscope:command` window event so a
 *  visible header pill can trigger it. */
export function SearchPalette({ rows, onNavigate }: Props) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const { toggle } = useTheme()
  const fuse = useMemo(() => makeFuse(rows), [rows])
  const results = useMemo(
    () => (q.trim() ? fuzzy(fuse, rows, q) : rows).slice(0, 20),
    [fuse, rows, q],
  )

  const actions = useMemo<Action[]>(() => {
    const nav = (tab: TabValue) => () => {
      onNavigate?.(tab)
      setOpen(false)
    }
    return [
      { id: 'go-overview', label: 'Go to Overview', hint: 'dashboard', keywords: 'overview home dashboard stats', icon: <LayoutGrid size={15} />, run: nav('overview') },
      { id: 'go-apps', label: 'Go to Applications', hint: 'pipeline', keywords: 'applications apply pipeline funnel status', icon: <Send size={15} />, run: nav('applications') },
      { id: 'go-all', label: 'Show all roles', hint: 'list', keywords: 'all roles list jobs', icon: <List size={15} />, run: nav('all') },
      { id: 'go-strong', label: 'Show Strong matches', hint: 'tier', keywords: 'strong best top tier matches', icon: <Star size={15} />, run: nav('Strong') },
      { id: 'go-good', label: 'Show Good matches', hint: 'tier', keywords: 'good tier matches', icon: <Star size={15} />, run: nav('Good') },
      { id: 'refresh-pull', label: 'Refresh \u2014 pull latest data', hint: 'reload', keywords: 'refresh reload update latest data sync pull fresh', icon: <DownloadCloud size={15} />, run: () => { setOpen(false); void pullLatestData() } },
      { id: 'refresh-scan', label: 'Scan new mail', hint: 'run', keywords: 'refresh scan mail inbox gmail run workflow action dispatch new', icon: <MailSearch size={15} />, run: () => { setOpen(false); void scanNewMail() } },
      { id: 'toggle-theme', label: 'Toggle light / dark theme', keywords: 'theme dark light mode appearance', icon: <SunMoon size={15} />, run: () => { toggle(); setOpen(false) } },
    ]
  }, [onNavigate, toggle])

  const shownActions = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return actions
    return actions.filter((a) => (a.label + ' ' + a.keywords).toLowerCase().includes(needle))
  }, [actions, q])

  useEffect(() => {
    const openPalette = () => {
      setQ('')
      setOpen(true)
    }
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !isTyping(e))) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener('keydown', onKey)
    window.addEventListener(COMMAND_EVENT, openPalette)
    return () => {
      document.removeEventListener('keydown', onKey)
      window.removeEventListener(COMMAND_EVENT, openPalette)
    }
  }, [])

  const openJob = (row: JobRow) => {
    window.open(row.url, '_blank', 'noreferrer')
    setOpen(false)
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className="w-full max-w-xl overflow-hidden rounded-[16px] border border-border bg-card shadow-[var(--shadow)]"
          >
            <Command shouldFilter={false} className="flex flex-col" loop>
              <div className="flex items-center gap-2 border-b border-border px-4">
                <Search size={16} className="opacity-50" />
                <Command.Input
                  autoFocus
                  value={q}
                  onValueChange={setQ}
                  placeholder="Search roles or run a command…"
                  className="flex-1 bg-transparent py-3.5 text-sm text-fg outline-none placeholder:text-mute"
                />
                <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] text-mute">esc</kbd>
              </div>
              <Command.List className="max-h-80 overflow-auto p-1.5">
                <Command.Empty className="px-3 py-6 text-center text-sm text-mute">
                  No matches.
                </Command.Empty>

                {shownActions.length > 0 && (
                  <Command.Group heading="Commands" className={HEADING}>
                    {shownActions.map((a) => (
                      <Command.Item
                        key={a.id}
                        value={`cmd:${a.id}`}
                        onSelect={a.run}
                        className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm transition data-[selected=true]:bg-card-h"
                      >
                        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-[7px] border border-border text-dim">
                          {a.icon}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-fg">{a.label}</span>
                        {a.hint && <span className="shrink-0 text-xs text-mute">{a.hint}</span>}
                        <ArrowRight size={13} className="shrink-0 opacity-30" />
                      </Command.Item>
                    ))}
                  </Command.Group>
                )}

                {results.length > 0 && (
                  <Command.Group heading="Roles" className={HEADING}>
                    {results.map((row) => (
                      <Command.Item
                        key={row.id}
                        value={row.id}
                        onSelect={() => openJob(row)}
                        className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm transition data-[selected=true]:bg-card-h"
                      >
                        <span
                          className="tnum w-8 shrink-0 text-center text-[13px] font-semibold"
                          style={{ color: TIER_COLOR[row.tier] }}
                        >
                          {Math.round(row.score)}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-fg">{row.title}</span>
                        <span className="shrink-0 truncate text-xs text-mute">{row.company}</span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                )}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
