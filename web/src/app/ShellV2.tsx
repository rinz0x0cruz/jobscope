import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Toaster } from 'sonner'
import { AppShell } from '@/app/AppShell'
import type { Section } from '@/app/AppShell'
import { Board } from '@/features/board'
import { Home } from '@/features/home'
import { Triage } from '@/features/triage'
import { Timeline } from '@/features/timeline'
import { Settings } from '@/features/settings'
import { CommandPalette } from '@/features/command'
import { buildBoard } from '@/lib/board'
import { buildBriefing } from '@/lib/briefing'
import { buildOverview } from '@/lib/overview'
import { buildTriage } from '@/lib/triage'
import { buildTimeline } from '@/lib/timeline'
import { filterData } from '@/lib/viewFilter'
import { scanNewMail } from '@/lib/refresh'
import { animate, viewTransition } from '@/ui'
import { JobDrawer } from '@/components/JobDrawer'
import type { DashboardData } from '@/lib/schema'

export interface ShellV2Props {
  data: DashboardData
  search: string
  onSearch: (v: string) => void
  onLock: () => void
  onOpenJob: (id: string) => void
  jobId?: string
  onCloseJob: () => void
}

const TITLES: Record<Section, string> = {
  home: 'Home',
  triage: 'To apply',
  board: 'Board',
  timeline: 'Timeline',
  settings: 'Settings',
}

/** Lens order for the digit (1-5) keyboard shortcuts - mirrors the sidebar. */
const LENS_ORDER: Section[] = ['home', 'triage', 'board', 'timeline', 'settings']

/** Toggle the v2 light/dark theme and persist the choice across reloads. */
function toggleTheme() {
  viewTransition(() => {
    const el = document.documentElement
    const nextLight = !el.classList.contains('light')
    el.classList.remove('dark', 'light')
    el.classList.add(nextLight ? 'light' : 'dark')
    try {
      localStorage.setItem('jobscope-theme', nextLight ? 'light' : 'dark')
    } catch {
      /* storage unavailable — the toggle still applies for this session */
    }
  })
}

/**
 * v2 "cockpit" shell. Owns lens navigation, the global-search view, and the ⌘K
 * command palette; renders a distinct surface per lens over the one hunt
 * pipeline. Keyboard: ⌘K/Ctrl-K palette, "/" focuses search, digits 1–6 switch
 * lenses.
 */
export function ShellV2({
  data,
  search,
  onSearch,
  onLock,
  onOpenJob,
  jobId,
  onCloseJob,
}: ShellV2Props) {
  const [lens, setLens] = useState<Section>('home')
  const [cmdOpen, setCmdOpen] = useState(false)

  const openJob = useMemo(() => data.rows.find((r) => r.id === jobId) ?? null, [data.rows, jobId])
  const openApp = useMemo(
    () => (jobId ? (data.applications ?? []).find((a) => a.job_id === jobId) ?? null : null),
    [data.applications, jobId],
  )

  // One filtered "view" drives every lens, so global search narrows the whole
  // cockpit consistently (the drawer + palette still see all rows).
  const view = useMemo(() => filterData(data, search), [data, search])
  const columns = useMemo(() => buildBoard(view), [view])
  const briefing = useMemo(() => buildBriefing(view), [view])
  const overviewModel = useMemo(() => buildOverview(view), [view])
  const triage = useMemo(() => buildTriage(view), [view])
  const timeline = useMemo(() => buildTimeline(view), [view])

  const refresh = useCallback(() => void scanNewMail(), [])

  // Gentle fade+rise of the lens content on each switch, then move focus to the
  // region so keyboard/SR users land on the new content. `animate` no-ops under
  // prefers-reduced-motion, leaving the final state.
  const contentRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    animate(
      contentRef.current,
      [
        { opacity: 0, transform: 'translateY(8px)' },
        { opacity: 1, transform: 'translateY(0)' },
      ],
      { duration: 280, easing: 'cubic-bezier(.2,0,0,1)' },
    )
    contentRef.current?.focus({ preventScroll: true })
  }, [lens])

  // Global keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        setCmdOpen((o) => !o)
        return
      }
      const el = document.activeElement
      const typing =
        el instanceof HTMLElement &&
        (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === '/') {
        const input = document.querySelector<HTMLInputElement>('input[type="search"]')
        if (input) {
          e.preventDefault()
          input.focus()
        }
        return
      }
      if (e.key >= '1' && e.key <= '6') {
        const target = LENS_ORDER[Number(e.key) - 1]
        if (target) {
          e.preventDefault()
          setLens(target)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <AppShell
        active={lens}
        onNavigate={setLens}
        title={TITLES[lens]}
        search={search}
        onSearch={onSearch}
        onOpenCommand={() => setCmdOpen(true)}
        onRefresh={refresh}
        onToggleTheme={toggleTheme}
        onLock={onLock}
        onProfile={() => setLens('settings')}
        profile={data.profile ? { name: `résumé: ${data.profile.resume}` } : null}
      >
        {/* Announce the active lens to assistive tech on each switch. */}
        <div aria-live="polite" className="sr-only">
          {TITLES[lens]}
        </div>
        <div ref={contentRef} tabIndex={-1} className="outline-none">
          {lens === 'home' ? (
            <Home
              model={overviewModel}
              briefing={briefing}
              apps={view.applications ?? []}
              onOpen={onOpenJob}
            />
          ) : lens === 'triage' ? (
            <Triage queue={triage} onOpen={onOpenJob} />
          ) : lens === 'board' ? (
            <Board columns={columns} onOpen={onOpenJob} />
          ) : lens === 'timeline' ? (
            <Timeline timeline={timeline} onOpen={onOpenJob} />
          ) : (
            <Settings
              profile={data.profile}
              generated={data.generated}
              total={data.total}
              onLock={onLock}
            />
          )}
        </div>
      </AppShell>

      <CommandPalette
        open={cmdOpen}
        onOpenChange={setCmdOpen}
        rows={data.rows}
        onNavigate={setLens}
        onOpenJob={onOpenJob}
        onRefresh={refresh}
        onToggleTheme={toggleTheme}
        onLock={onLock}
      />

      <JobDrawer
        job={openJob}
        application={openApp}
        allRows={data.rows}
        onOpen={onOpenJob}
        onClose={onCloseJob}
      />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: 'var(--card)',
            color: 'var(--fg)',
            border: '1px solid var(--border)',
          },
        }}
      />
    </>
  )
}
