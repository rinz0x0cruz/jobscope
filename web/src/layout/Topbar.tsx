import { Lock, Menu, RefreshCw, Search, SunMedium, User } from 'lucide-react'
import { IconButton, Input } from '@/ui'

export interface TopbarProps {
  /** Page title shown at the left of the bar. */
  title: string
  /** Controlled value of the global search field. */
  search: string
  /** Fired with the new query on every search keystroke. */
  onSearch: (value: string) => void
  /** Opens the mobile navigation drawer; the trigger renders only below `md`. */
  onMenu?: () => void
  /** Opens the command palette (the ⌘K hint and the mobile search button). */
  onOpenCommand?: () => void
  /** Optional refresh handler; the action always renders (no-op when omitted). */
  onRefresh?: () => void
  /** Optional theme toggle; the action always renders (no-op when omitted). */
  onToggleTheme?: () => void
  /** Optional session re-lock; the action always renders (no-op when omitted). */
  onLock?: () => void
  /** Optional profile action (opens Settings); hidden on mobile. */
  onProfile?: () => void
}

/**
 * Sticky top bar: an optional mobile menu button, the page title, a global
 * search field (with a ⌘K palette hint; a search button below `sm`), and quick
 * actions (refresh, theme, lock, profile). Presentational only.
 */
export function Topbar({
  title,
  search,
  onSearch,
  onMenu,
  onOpenCommand,
  onRefresh,
  onToggleTheme,
  onLock,
  onProfile,
}: TopbarProps) {
  return (
    <header className="sticky top-0 z-10 flex h-16 items-center gap-3 border-b border-line bg-panel/80 px-4 backdrop-blur sm:gap-4 sm:px-6">
      {onMenu && (
        <IconButton label="Open menu" onClick={onMenu} className="md:hidden">
          <Menu size={18} aria-hidden="true" />
        </IconButton>
      )}
      <h1 className="truncate font-display text-lg font-semibold text-ink">{title}</h1>

      <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
        <div className="relative hidden w-64 sm:block">
          <Search
            size={16}
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
          />
          <Input
            type="search"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search roles…"
            aria-label="Search"
            className="pl-9 pr-12"
          />
          {onOpenCommand && (
            <button
              type="button"
              onClick={onOpenCommand}
              aria-label="Open command menu"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-3 transition-colors hover:border-line-strong hover:text-ink"
            >
              ⌘K
            </button>
          )}
        </div>
        {onOpenCommand && (
          <IconButton label="Search" onClick={onOpenCommand} className="sm:hidden">
            <Search size={18} aria-hidden="true" />
          </IconButton>
        )}

        <IconButton label="Refresh" onClick={onRefresh}>
          <RefreshCw size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Toggle theme" onClick={onToggleTheme}>
          <SunMedium size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Lock" onClick={onLock}>
          <Lock size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Profile" onClick={onProfile} className="hidden sm:inline-flex">
          <User size={18} aria-hidden="true" />
        </IconButton>
      </div>
    </header>
  )
}
