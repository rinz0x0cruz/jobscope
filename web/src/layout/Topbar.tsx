import { Lock, RefreshCw, Search, SunMedium, User } from 'lucide-react'
import { IconButton, Input } from '@/ui'

export interface TopbarProps {
  /** Page title shown at the left of the bar. */
  title: string
  /** Controlled value of the global search field. */
  search: string
  /** Fired with the new query on every search keystroke. */
  onSearch: (value: string) => void
  /** Optional refresh handler; the action always renders (no-op when omitted). */
  onRefresh?: () => void
  /** Optional theme toggle; the action always renders (no-op when omitted). */
  onToggleTheme?: () => void
  /** Optional session re-lock; the action always renders (no-op when omitted). */
  onLock?: () => void
}

/**
 * Sticky top bar: page title, a global search field, and quick actions
 * (refresh, theme, lock, profile). Presentational only — each action is a
 * passed-in callback that stays harmless when its prop is undefined.
 */
export function Topbar({
  title,
  search,
  onSearch,
  onRefresh,
  onToggleTheme,
  onLock,
}: TopbarProps) {
  return (
    <header className="sticky top-0 z-10 flex h-16 items-center gap-4 border-b border-line bg-panel/80 px-6 backdrop-blur">
      <h1 className="font-display text-lg font-semibold text-ink">{title}</h1>

      <div className="ml-auto flex items-center gap-2">
        <div className="relative w-64">
          <Search
            size={16}
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3"
          />
          <Input
            type="search"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search"
            aria-label="Search"
            className="pl-9"
          />
        </div>

        <IconButton label="Refresh" onClick={onRefresh}>
          <RefreshCw size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Toggle theme" onClick={onToggleTheme}>
          <SunMedium size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Lock" onClick={onLock}>
          <Lock size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label="Profile">
          <User size={18} aria-hidden="true" />
        </IconButton>
      </div>
    </header>
  )
}
