import { useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {
  Activity,
  Building2,
  CloudUpload,
  BriefcaseBusiness,
  Compass,
  ListFilter,
  Lock,
  MoreHorizontal,
  MailSearch,
  Send,
  Search,
  Settings,
  SunMedium,
  Workflow,
} from 'lucide-react'
import { IconButton, Input } from '@/ui'
import type { ViewValue } from '@/lib/urlState'

export interface AppShellProps {
  active: ViewValue
  onNavigate: (view: ViewValue) => void
  search: string
  onSearch: (value: string) => void
  onOpenCommand?: () => void
  onRefresh?: () => void
  onToggleTheme?: () => void
  onLock?: () => void
  pendingChanges?: number
  onSyncChanges?: () => void
  campaignsAvailable?: boolean
  children: ReactNode
}

const NAV_ITEMS: Array<{ value: ViewValue; label: string; Icon: typeof ListFilter }> = [
  { value: 'review', label: 'Review', Icon: ListFilter },
  { value: 'companies', label: 'Companies', Icon: Building2 },
  { value: 'campaigns', label: 'Campaigns', Icon: Send },
  { value: 'pipeline', label: 'Pipeline', Icon: Workflow },
  { value: 'applications', label: 'Applications', Icon: BriefcaseBusiness },
  { value: 'activity', label: 'Activity', Icon: Activity },
  { value: 'settings', label: 'Settings', Icon: Settings },
]

const MOBILE_VIEWS: ViewValue[] = ['review', 'companies', 'pipeline', 'applications']

const NAV_SECTIONS: Array<{ label: string; views: ViewValue[] }> = [
  { label: 'Workspace', views: ['review', 'companies'] },
  { label: 'Progress', views: ['campaigns', 'pipeline', 'applications', 'activity'] },
  { label: 'System', views: ['settings'] },
]

function DesktopSidebar({
  active,
  onNavigate,
  onToggleTheme,
  onLock,
  campaignsAvailable,
}: {
  active: ViewValue
  onNavigate: (view: ViewValue) => void
  onToggleTheme?: () => void
  onLock?: () => void
  campaignsAvailable: boolean
}) {
  return (
    <aside className="hidden h-dvh min-h-0 flex-col border-r border-line bg-panel lg:flex">
      <button
        type="button"
        onClick={() => onNavigate('review')}
        className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
        aria-label="Open review"
      >
        <span className="grid h-9 w-9 place-items-center rounded-md bg-brand text-white shadow-sm">
          <Compass size={18} strokeWidth={2} aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block truncate font-display text-[16px] font-semibold text-ink">jobscope</span>
          <span className="block text-[10px] font-medium uppercase text-ink-3">Career workspace</span>
        </span>
      </button>

      <nav aria-label="Primary" className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        {NAV_SECTIONS.map((section, sectionIndex) => (
          <div key={section.label} className={sectionIndex ? 'mt-5' : ''}>
            <p className="mb-1.5 px-2 text-[9px] font-semibold uppercase text-ink-3">{section.label}</p>
            <div className="space-y-1">
              {section.views.filter((value) => value !== 'campaigns' || campaignsAvailable).map((value) => {
                const item = NAV_ITEMS.find((candidate) => candidate.value === value)
                if (!item) return null
                const { label, Icon } = item
                const selected = active === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => onNavigate(value)}
                    aria-current={selected ? 'page' : undefined}
                    className={`flex h-10 w-full items-center gap-3 rounded-md px-3 text-left text-[13px] font-medium outline-none transition-colors ${
                      selected
                        ? 'bg-brand-weak text-brand shadow-[inset_3px_0_var(--brand-coral)]'
                        : 'text-ink-2 hover:bg-inset hover:text-ink'
                    }`}
                  >
                    <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
                    <span>{label}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-line p-3">
        <div className={`grid gap-1 ${onLock ? 'grid-cols-2' : 'grid-cols-1'}`}>
          <button
            type="button"
            onClick={onToggleTheme}
            className="flex h-10 items-center justify-center gap-2 rounded-md text-[11px] font-medium text-ink-2 hover:bg-inset hover:text-ink"
          >
            <SunMedium size={15} aria-hidden="true" /> Theme
          </button>
          {onLock && <button
            type="button"
            onClick={onLock}
            className="flex h-10 items-center justify-center gap-2 rounded-md text-[11px] font-medium text-ink-2 hover:bg-inset hover:text-ink"
          >
            <Lock size={15} aria-hidden="true" /> Lock
          </button>}
        </div>
      </div>
    </aside>
  )
}

function MobileNav({ active, onNavigate, campaignsAvailable }: { active: ViewValue; onNavigate: (view: ViewValue) => void; campaignsAvailable: boolean }) {
  const [moreOpen, setMoreOpen] = useState(false)
  const moreActive = !MOBILE_VIEWS.includes(active)
  return (
    <>
      <nav aria-label="Mobile primary" className="grid h-16 grid-cols-5 border-t border-line bg-panel/95 shadow-[0_-8px_24px_-20px_rgba(0,0,0,.55)] backdrop-blur">
        {NAV_ITEMS.filter((item) => MOBILE_VIEWS.includes(item.value)).map(({ value, label, Icon }) => {
          const selected = active === value
          return (
            <button
              key={value}
              type="button"
              onClick={() => onNavigate(value)}
              aria-current={selected ? 'page' : undefined}
              className={`relative flex flex-col items-center justify-center gap-1 text-[10px] font-medium outline-none ${selected ? 'text-brand' : 'text-ink-3'}`}
            >
              <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
              <span>{label === 'Applications' ? 'Apps' : label}</span>
              {selected && <span className="absolute inset-x-3 top-0 h-0.5 bg-brand" aria-hidden="true" />}
            </button>
          )
        })}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          aria-current={moreActive ? 'page' : undefined}
          className={`relative flex flex-col items-center justify-center gap-1 text-[10px] font-medium outline-none ${moreActive ? 'text-brand' : 'text-ink-3'}`}
        >
          <MoreHorizontal size={18} strokeWidth={1.8} aria-hidden="true" />
          <span>More</span>
          {moreActive && <span className="absolute inset-x-3 top-0 h-0.5 bg-brand" aria-hidden="true" />}
        </button>
      </nav>
      <Dialog.Root open={moreOpen} onOpenChange={setMoreOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45" />
          <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 border-t border-line bg-panel p-4 outline-none">
            <Dialog.Title className="mb-2 text-[12px] font-semibold uppercase text-ink-3">More views</Dialog.Title>
            {NAV_ITEMS.filter((item) => !MOBILE_VIEWS.includes(item.value) && (item.value !== 'campaigns' || campaignsAvailable)).map(({ value, label, Icon }) => (
              <button
                key={value}
                type="button"
                onClick={() => { setMoreOpen(false); onNavigate(value) }}
                className="flex h-12 w-full items-center gap-3 border-t border-line px-2 text-left text-[14px] text-ink first:border-t-0"
              >
                <Icon size={18} aria-hidden="true" className="text-ink-3" />{label}
              </button>
            ))}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  )
}

export function AppShell({
  active,
  onNavigate,
  search,
  onSearch,
  onOpenCommand,
  onRefresh,
  onToggleTheme,
  onLock,
  pendingChanges = 0,
  onSyncChanges,
  campaignsAvailable = false,
  children,
}: AppShellProps) {
  const title = NAV_ITEMS.find((item) => item.value === active)?.label ?? 'Feed'
  return (
    <div className="grid h-dvh min-h-0 overflow-hidden bg-paper font-sans text-ink lg:grid-cols-[224px_minmax(0,1fr)]">
      <DesktopSidebar
        active={active}
        onNavigate={onNavigate}
        onToggleTheme={onToggleTheme}
        onLock={onLock}
        campaignsAvailable={campaignsAvailable}
      />

      <div className="flex min-h-0 min-w-0 flex-col">
        <header className="z-30 shrink-0 border-b border-line bg-panel">
          <div className="flex h-16 items-center gap-3 px-3 sm:px-5 lg:px-6">
          <button
            type="button"
            onClick={() => onNavigate('review')}
            aria-label="Open review"
            className="flex shrink-0 items-center rounded-md outline-none focus-visible:ring-2 focus-visible:ring-brand lg:hidden"
          >
            <span className="grid h-8 w-8 place-items-center rounded-md bg-brand text-white">
              <Compass size={17} strokeWidth={2} aria-hidden="true" />
            </span>
          </button>

          <h1 className="sr-only min-w-24 shrink-0 font-display text-xl font-semibold text-ink sm:not-sr-only">
            {title}
          </h1>

          <div className="relative ml-auto w-full max-w-xl">
            <Search
              size={15}
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
            />
            <Input
              type="search"
              value={search}
              onChange={(event) => onSearch(event.target.value)}
              placeholder="Search roles, companies, locations"
              aria-label="Search roles"
              className="h-9 rounded-md border-line bg-paper pl-9 pr-14 text-[13px] shadow-none"
            />
            {onOpenCommand && (
              <button
                type="button"
                onClick={onOpenCommand}
                aria-label="Open command menu"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md border border-line px-1.5 py-0.5 font-mono text-[9px] text-ink-3 hover:text-ink"
              >
                ⌘K
              </button>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-0.5">
            {pendingChanges > 0 && onSyncChanges && (
              <button
                type="button"
                onClick={onSyncChanges}
                aria-label={`Sync ${pendingChanges} queued change${pendingChanges === 1 ? '' : 's'}`}
                className="relative inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-brand hover:bg-brand-weak"
              >
                <CloudUpload size={16} aria-hidden="true" />
                <span className="hidden sm:inline">Sync {pendingChanges}</span>
                <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-brand px-1 text-[9px] text-white sm:hidden">{pendingChanges}</span>
              </button>
            )}
            <button
              type="button"
              onClick={onRefresh}
              aria-label="Scan Gmail"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-paper px-2.5 text-[11px] font-semibold text-ink-2 transition hover:border-line-strong hover:text-ink"
            >
              <MailSearch size={16} aria-hidden="true" />
              <span className="hidden sm:inline">Scan Gmail</span>
            </button>
            <IconButton label="Toggle theme" onClick={onToggleTheme} className="hidden sm:inline-flex lg:hidden">
              <SunMedium size={17} aria-hidden="true" />
            </IconButton>
            {onLock && <IconButton label="Lock" onClick={onLock} className="lg:hidden">
              <Lock size={17} aria-hidden="true" />
            </IconButton>}
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto">{children}</main>
      <div className="fixed inset-x-0 bottom-0 z-30 lg:hidden">
        <MobileNav active={active} onNavigate={onNavigate} campaignsAvailable={campaignsAvailable} />
      </div>
      </div>
    </div>
  )
}
