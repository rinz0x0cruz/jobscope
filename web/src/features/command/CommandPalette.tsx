// ⌘K command palette: jump between lenses, run quick actions, and fuzzy-search
// jobs to open in the drawer. Built on Radix Dialog (focus trap + a11y) wrapping
// cmdk (list/keyboard nav) with fuse.js for the job search. Token-driven styling.

import { useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Command } from 'cmdk'
import Fuse from 'fuse.js'
import {
  Briefcase,
  Building2,
  CalendarClock,
  Columns3,
  Home,
  Inbox,
  Lock,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  SunMedium,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ViewValue } from '@/lib/urlState'
import type { JobRow } from '@/lib/schema'

export interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  rows: JobRow[]
  onNavigate: (section: ViewValue) => void
  onOpenJob: (id: string) => void
  onRefresh: () => void
  onToggleTheme: () => void
  onLock: () => void
}

const LENSES: { section: ViewValue; label: string; Icon: LucideIcon }[] = [
  { section: 'review', label: 'Review', Icon: Home },
  { section: 'companies', label: 'Companies', Icon: Building2 },
  { section: 'pipeline', label: 'Pipeline', Icon: Inbox },
  { section: 'applications', label: 'Applications', Icon: Columns3 },
  { section: 'activity', label: 'Activity', Icon: CalendarClock },
  { section: 'settings', label: 'Settings', Icon: SettingsIcon },
]

const ITEM =
  'flex cursor-pointer items-center gap-2.5 rounded-card px-2.5 py-2 text-sm text-ink-2 ' +
  'data-[selected=true]:bg-inset data-[selected=true]:text-ink'

export function CommandPalette({
  open,
  onOpenChange,
  rows,
  onNavigate,
  onOpenJob,
  onRefresh,
  onToggleTheme,
  onLock,
}: CommandPaletteProps) {
  const [q, setQ] = useState('')

  const fuse = useMemo(
    () => new Fuse(rows, { keys: ['company', 'title', 'location'], threshold: 0.4, ignoreLocation: true }),
    [rows],
  )
  const jobs = useMemo(() => {
    if (!q.trim()) return rows.slice(0, 6)
    return fuse.search(q).slice(0, 8).map((r) => r.item)
  }, [q, fuse, rows])

  const run = (fn: () => void) => {
    onOpenChange(false)
    fn()
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:[animation:cmd-overlay-in_.15s_ease] motion-reduce:animate-none" />
        <Dialog.Content
          aria-label="Command menu"
          className="fixed left-1/2 top-[14%] z-50 w-[92vw] max-w-xl -translate-x-1/2 data-[state=open]:[animation:cmd-pop-in_.16s_cubic-bezier(.2,0,0,1)] motion-reduce:animate-none"
        >
          <Dialog.Title className="sr-only">Command menu</Dialog.Title>
          <Command
            shouldFilter={false}
            className="overflow-hidden rounded-card border border-line bg-panel shadow-[var(--shadow-panel)] [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-ink-3"
          >
            <div className="flex items-center gap-2 border-b border-line px-3.5">
              <Search size={16} aria-hidden="true" className="shrink-0 text-ink-3" />
              <Command.Input
                value={q}
                onValueChange={setQ}
                placeholder="Search jobs or jump to…"
                className="h-12 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
              />
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              <Command.Empty className="py-8 text-center text-sm text-ink-3">
                No matches.
              </Command.Empty>

              <Command.Group heading="Go to">
                {LENSES.map(({ section, label, Icon }) => (
                  <Command.Item
                    key={section}
                    value={`go ${label}`}
                    onSelect={() => run(() => onNavigate(section))}
                    className={ITEM}
                  >
                    <Icon size={16} aria-hidden="true" className="text-ink-3" />
                    <span>{label}</span>
                  </Command.Item>
                ))}
              </Command.Group>

              <Command.Group heading="Actions">
                <Command.Item value="refresh scan mail" onSelect={() => run(onRefresh)} className={ITEM}>
                  <RefreshCw size={16} aria-hidden="true" className="text-ink-3" />
                  <span>Refresh · scan mail</span>
                </Command.Item>
                <Command.Item value="toggle theme dark light" onSelect={() => run(onToggleTheme)} className={ITEM}>
                  <SunMedium size={16} aria-hidden="true" className="text-ink-3" />
                  <span>Toggle theme</span>
                </Command.Item>
                <Command.Item value="lock dashboard sign out" onSelect={() => run(onLock)} className={ITEM}>
                  <Lock size={16} aria-hidden="true" className="text-ink-3" />
                  <span>Lock dashboard</span>
                </Command.Item>
              </Command.Group>

              {jobs.length > 0 && (
                <Command.Group heading={q.trim() ? 'Jobs' : 'Recent roles'}>
                  {jobs.map((j) => (
                    <Command.Item
                      key={j.id}
                      value={`job ${j.id} ${j.company} ${j.title}`}
                      onSelect={() => run(() => onOpenJob(j.id))}
                      className={ITEM}
                    >
                      <Briefcase size={16} aria-hidden="true" className="shrink-0 text-ink-3" />
                      <span className="truncate">
                        <span className="text-ink">{j.company}</span>
                        <span className="text-ink-3"> — {j.title}</span>
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
