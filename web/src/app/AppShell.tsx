import type { ReactNode } from 'react'
import {
  Activity,
  BriefcaseBusiness,
  Compass,
  ListFilter,
  Lock,
  RefreshCw,
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
  children: ReactNode
}

const NAV_ITEMS: Array<{ value: ViewValue; label: string; Icon: typeof ListFilter }> = [
  { value: 'feed', label: 'Feed', Icon: ListFilter },
  { value: 'pipeline', label: 'Pipeline', Icon: Workflow },
  { value: 'applications', label: 'Applications', Icon: BriefcaseBusiness },
  { value: 'activity', label: 'Activity', Icon: Activity },
  { value: 'settings', label: 'Settings', Icon: Settings },
]

function Nav({
  active,
  onNavigate,
  mobile = false,
}: {
  active: ViewValue
  onNavigate: (view: ViewValue) => void
  mobile?: boolean
}) {
  return (
    <nav
      aria-label={mobile ? 'Mobile primary' : 'Primary'}
      className={
        mobile
          ? 'grid h-16 grid-cols-5 border-t border-line bg-panel'
          : 'hidden h-10 items-stretch gap-1 border-t border-line px-4 sm:flex lg:px-6'
      }
    >
      {NAV_ITEMS.map(({ value, label, Icon }) => {
        const selected = active === value
        return (
          <button
            key={value}
            type="button"
            onClick={() => onNavigate(value)}
            aria-current={selected ? 'page' : undefined}
            className={`relative flex items-center justify-center gap-1.5 px-3 text-[11px] font-medium outline-none transition-colors sm:justify-start ${
              selected ? 'text-brand' : 'text-ink-3 hover:text-ink'
            }`}
          >
            <Icon size={mobile ? 18 : 14} strokeWidth={1.8} aria-hidden="true" />
            <span className={mobile ? 'text-[10px]' : ''}>
              {mobile && label === 'Applications' ? 'Apps' : label}
            </span>
            {selected && (
              <span
                aria-hidden="true"
                className={`absolute bg-brand ${mobile ? 'inset-x-3 top-0 h-0.5' : 'inset-x-2 bottom-0 h-0.5'}`}
              />
            )}
          </button>
        )
      })}
    </nav>
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
  children,
}: AppShellProps) {
  const title = NAV_ITEMS.find((item) => item.value === active)?.label ?? 'Feed'
  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-paper font-sans text-ink">
      <header className="z-30 shrink-0 border-b border-line bg-panel">
        <div className="flex min-h-14 items-center gap-3 px-3 sm:px-4 lg:px-6">
          <button
            type="button"
            onClick={() => onNavigate('feed')}
            aria-label="Open feed"
            className="flex shrink-0 items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <span className="grid h-8 w-8 place-items-center rounded-md bg-ink text-panel">
              <Compass size={17} strokeWidth={2} aria-hidden="true" />
            </span>
            <span className="hidden font-display text-[15px] font-semibold sm:inline">jobscope</span>
          </button>

          <div className="relative mx-auto w-full max-w-2xl">
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
              className="h-9 rounded-full bg-paper pl-9 pr-14 text-[13px] shadow-none"
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
            <IconButton label="Refresh" onClick={onRefresh}>
              <RefreshCw size={17} aria-hidden="true" />
            </IconButton>
            <IconButton label="Toggle theme" onClick={onToggleTheme} className="hidden sm:inline-flex">
              <SunMedium size={17} aria-hidden="true" />
            </IconButton>
            <IconButton label="Lock" onClick={onLock}>
              <Lock size={17} aria-hidden="true" />
            </IconButton>
          </div>
        </div>
        <h1 aria-live="polite" className="sr-only">{title}</h1>
        <Nav active={active} onNavigate={onNavigate} />
      </header>

      <main className="min-h-0 flex-1 overflow-auto">{children}</main>
      <div className="fixed inset-x-0 bottom-0 z-30 sm:hidden">
        <Nav active={active} onNavigate={onNavigate} mobile />
      </div>
    </div>
  )
}
