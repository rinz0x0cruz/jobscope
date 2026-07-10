import type { CSSProperties, ReactNode } from 'react'
import { Sidebar } from '@/layout/Sidebar'
import type { Section } from '@/layout/Sidebar'
import { Topbar } from '@/layout/Topbar'

export type { Section }

export interface AppShellProps {
  active: Section
  onNavigate: (s: Section) => void
  title: string // page title shown in the topbar
  search: string
  onSearch: (v: string) => void
  onRefresh?: () => void
  onToggleTheme?: () => void
  onLock?: () => void // re-lock the session (auth gate comes later)
  profile?: { name?: string; completion?: number } | null // bottom mini-card
  children: ReactNode // the routed page content
}

/** Loose-typed so a future View Transition can target the content region. */
const MAIN_STYLE = { viewTransitionName: 'shell-main' } as CSSProperties

/**
 * v2 application shell: a persistent left {@link Sidebar} plus a right column of
 * a sticky {@link Topbar} and a scrollable `<main>` that renders the routed
 * page. Purely presentational — all state and side effects are lifted to props.
 */
export function AppShell({
  active,
  onNavigate,
  title,
  search,
  onSearch,
  onRefresh,
  onToggleTheme,
  onLock,
  profile,
  children,
}: AppShellProps) {
  return (
    <div className="flex min-h-screen bg-paper font-sans text-ink">
      <Sidebar active={active} onNavigate={onNavigate} profile={profile} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          search={search}
          onSearch={onSearch}
          onRefresh={onRefresh}
          onToggleTheme={onToggleTheme}
          onLock={onLock}
        />
        <main style={MAIN_STYLE} className="w-full px-6 py-6">
          {children}
        </main>
      </div>
    </div>
  )
}
