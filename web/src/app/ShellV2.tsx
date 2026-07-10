import { useEffect, useMemo, useRef, useState } from 'react'
import { Toaster } from 'sonner'
import { AppShell } from '@/app/AppShell'
import type { Section } from '@/app/AppShell'
import { Board } from '@/features/board'
import { Briefing } from '@/features/briefing'
import { Triage } from '@/features/triage'
import { Timeline } from '@/features/timeline'
import { buildBoard, filterBoard } from '@/lib/board'
import { buildBriefing } from '@/lib/briefing'
import { buildTriage } from '@/lib/triage'
import { buildTimeline } from '@/lib/timeline'
import { Card, animate, viewTransition } from '@/ui'
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
  briefing: 'Briefing',
  triage: 'To apply',
  board: 'Board',
  timeline: 'Timeline',
  settings: 'Settings',
}

// One-line intent for each not-yet-built lens (rendered as an intentional
// placeholder, not the old feature content).
const SOON: Record<Section, string> = {
  briefing:
    'A single-scroll “state of your search” — a written brief of what moved this week and what needs you.',
  triage:
    'A keyboard-first queue of today’s decisions — new matches and inbound signals, one at a time.',
  board: '',
  timeline:
    'A time-centric agenda — upcoming interviews, follow-ups due, and the chronological track of your hunt.',
  settings: 'Preferences, résumé, and publishing controls.',
}

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

function ComingSoon({ section }: { section: Section }) {
  return (
    <div className="mx-auto max-w-md py-20">
      <Card>
        <div className="text-center">
          <div className="text-xs font-semibold uppercase tracking-wide text-brand">
            Coming next
          </div>
          <h2 className="mt-2 font-display text-xl font-semibold text-ink">{TITLES[section]}</h2>
          <p className="mt-2 text-sm text-ink-2">{SOON[section]}</p>
        </div>
      </Card>
    </div>
  )
}

/**
 * v2 "cockpit" shell. Owns its own lens navigation (Briefing / Triage / Board /
 * Timeline / Settings) — decoupled from the legacy tab/URL state — and renders a
 * genuinely new surface per lens over the one hunt pipeline. Only the Board lens
 * is live; the others are intentional placeholders for the phased rebuild.
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
  const [lens, setLens] = useState<Section>('briefing')
  const openJob = useMemo(() => data.rows.find((r) => r.id === jobId) ?? null, [data.rows, jobId])
  const columns = useMemo(() => filterBoard(buildBoard(data), search), [data, search])
  const briefing = useMemo(() => buildBriefing(data), [data])
  const triage = useMemo(() => buildTriage(data), [data])
  const timeline = useMemo(() => buildTimeline(data), [data])

  // Gentle fade+rise of the lens content on each switch (and initial mount).
  // `animate` is a no-op under prefers-reduced-motion, leaving the final state.
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
  }, [lens])

  return (
    <>
      <AppShell
        active={lens}
        onNavigate={setLens}
        title={TITLES[lens]}
        search={search}
        onSearch={onSearch}
        onToggleTheme={toggleTheme}
        onLock={onLock}
        profile={data.profile ? { name: `résumé: ${data.profile.resume}` } : null}
      >
        <div ref={contentRef}>
          {lens === 'briefing' ? (
            <Briefing briefing={briefing} onOpen={onOpenJob} />
          ) : lens === 'triage' ? (
            <Triage queue={triage} onOpen={onOpenJob} query={search} />
          ) : lens === 'board' ? (
            <Board columns={columns} onOpen={onOpenJob} />
          ) : lens === 'timeline' ? (
            <Timeline timeline={timeline} onOpen={onOpenJob} />
          ) : (
            <ComingSoon section={lens} />
          )}
        </div>
      </AppShell>
      <JobDrawer job={openJob} allRows={data.rows} onOpen={onOpenJob} onClose={onCloseJob} />
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
