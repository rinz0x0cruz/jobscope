import {
  CalendarClock,
  Columns3,
  Compass,
  Inbox,
  Newspaper,
  Settings,
  User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** The five top-level lenses rendered in the app shell's left sidebar. Each is a
 *  distinct view onto the one hunt pipeline, not a separate feature area. */
export type Section = 'briefing' | 'triage' | 'board' | 'timeline' | 'settings'

/** Bottom mini-card describing the signed-in user's profile completion. */
export interface SidebarProfile {
  name?: string
  completion?: number
}

export interface SidebarProps {
  /** Currently selected section — highlighted and marked `aria-current="page"`. */
  active: Section
  /** Fired with the chosen section when a nav item is activated. */
  onNavigate: (section: Section) => void
  /** Optional profile mini-card pinned to the bottom; omitted when nullish. */
  profile?: SidebarProfile | null
}

interface NavItem {
  section: Section
  label: string
  Icon: LucideIcon
}

const NAV_ITEMS: readonly NavItem[] = [
  { section: 'briefing', label: 'Briefing', Icon: Newspaper },
  { section: 'triage', label: 'To apply', Icon: Inbox },
  { section: 'board', label: 'Board', Icon: Columns3 },
  { section: 'timeline', label: 'Timeline', Icon: CalendarClock },
  { section: 'settings', label: 'Settings', Icon: Settings },
]

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * Persistent, full-height left navigation: brand mark, the five primary
 * sections, and an optional profile-completion mini-card. Presentational only —
 * navigation intent is delegated to `onNavigate`.
 */
export function Sidebar({ active, onNavigate, profile }: SidebarProps) {
  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col self-start border-r border-line bg-panel">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-card bg-brand text-white">
          <Compass size={18} aria-hidden="true" />
        </span>
        <span className="font-display text-lg font-semibold text-ink">jobscope</span>
      </div>

      <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 px-3 py-3">
        {NAV_ITEMS.map(({ section, label, Icon }) => {
          const isActive = section === active
          return (
            <button
              key={section}
              type="button"
              onClick={() => onNavigate(section)}
              aria-current={isActive ? 'page' : undefined}
              className={cx(
                'flex w-full items-center gap-2.5 rounded-card px-3 py-2 text-sm transition-colors',
                'outline-none focus-visible:ring-2 focus-visible:ring-brand',
                isActive
                  ? 'bg-brand-weak font-medium text-brand'
                  : 'text-ink-2 hover:bg-inset hover:text-ink',
              )}
            >
              <Icon size={18} aria-hidden="true" className="shrink-0" />
              <span>{label}</span>
            </button>
          )
        })}
      </nav>

      {profile != null && (
        <div className="p-3">
          <div className="flex items-center gap-3 rounded-card border border-line p-3">
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-inset text-ink-2">
              <User size={18} aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              {profile.name != null && profile.name !== '' && (
                <div className="truncate text-sm text-ink">{profile.name}</div>
              )}
              {typeof profile.completion === 'number' && (
                <>
                  <div
                    className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-inset"
                    aria-hidden="true"
                  >
                    <div
                      className="h-full rounded-full bg-brand"
                      style={{ width: `${profile.completion}%` }}
                    />
                  </div>
                  <div className="mt-1 text-[11px] text-ink-3">
                    {profile.completion}% complete
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
