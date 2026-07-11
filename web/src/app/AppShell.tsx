import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Compass } from 'lucide-react'
import { NavList, Sidebar } from '@/layout/Sidebar'
import type { Section } from '@/layout/Sidebar'
import { Topbar } from '@/layout/Topbar'

export type { Section }

export interface AppShellProps {
  active: Section
  onNavigate: (s: Section) => void
  title: string // page title shown in the topbar
  search: string
  onSearch: (v: string) => void
  onOpenCommand?: () => void
  onRefresh?: () => void
  onToggleTheme?: () => void
  onLock?: () => void // re-lock the session
  onProfile?: () => void // open Settings
  profile?: { name?: string; completion?: number } | null // bottom mini-card
  children: ReactNode // the routed page content
}

/** Loose-typed so a future View Transition can target the content region. */
const MAIN_STYLE = { viewTransitionName: 'shell-main' } as CSSProperties

/**
 * v2 application shell: a persistent left {@link Sidebar} (desktop) plus a
 * right column of a sticky {@link Topbar} and a scrollable `<main>`. On mobile
 * the sidebar collapses into a slide-in {@link Dialog} drawer opened from the
 * topbar menu button. Purely presentational — state/effects live in props.
 */
export function AppShell({
  active,
  onNavigate,
  title,
  search,
  onSearch,
  onOpenCommand,
  onRefresh,
  onToggleTheme,
  onLock,
  onProfile,
  profile,
  children,
}: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigateMobile = (s: Section) => {
    onNavigate(s)
    setMobileOpen(false)
  }

  return (
    <div className="flex min-h-screen bg-paper font-sans text-ink">
      <Sidebar active={active} onNavigate={onNavigate} profile={profile} />

      <Dialog.Root open={mobileOpen} onOpenChange={setMobileOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm data-[state=open]:[animation:cmd-overlay-in_.15s_ease] motion-reduce:animate-none md:hidden" />
          <Dialog.Content
            aria-label="Navigation"
            className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-panel data-[state=open]:[animation:drawer-in_.2s_cubic-bezier(.2,0,0,1)] motion-reduce:animate-none md:hidden"
          >
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <div className="flex h-16 items-center gap-2.5 px-5">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-card bg-brand text-white">
                <Compass size={18} aria-hidden="true" />
              </span>
              <span className="font-display text-lg font-semibold text-ink">jobscope</span>
            </div>
            <NavList active={active} onNavigate={navigateMobile} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          search={search}
          onSearch={onSearch}
          onMenu={() => setMobileOpen(true)}
          onOpenCommand={onOpenCommand}
          onRefresh={onRefresh}
          onToggleTheme={onToggleTheme}
          onLock={onLock}
          onProfile={onProfile}
        />
        <main style={MAIN_STYLE} className="w-full px-4 py-5 sm:px-6 sm:py-6">
          {children}
        </main>
      </div>
    </div>
  )
}
