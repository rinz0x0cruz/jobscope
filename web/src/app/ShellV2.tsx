import { useCallback, useEffect, useMemo, useState } from 'react'
import { Toaster } from 'sonner'
import { AppShell } from '@/app/AppShell'
import { Board } from '@/features/board'
import { FeedView } from '@/features/feed'
import { PipelinePreview, PipelineView } from '@/features/pipeline'
import { Timeline } from '@/features/timeline'
import { Settings } from '@/features/settings'
import { CommandPalette } from '@/features/command'
import { ApplicationReader, JobDrawer, RoleReader } from '@/components/JobDrawer'
import { buildBoard } from '@/lib/board'
import { buildFeed } from '@/lib/feed'
import { buildTimeline } from '@/lib/timeline'
import { filterData } from '@/lib/viewFilter'
import { activeView, type SearchState, type ViewValue } from '@/lib/urlState'
import { scanNewMail } from '@/lib/refresh'
import { viewTransition } from '@/ui'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import type { DashboardData } from '@/lib/schema'

export interface ShellV2Props {
  data: DashboardData
  state: SearchState
  onStateChange: (patch: Partial<SearchState>, options?: { replace?: boolean }) => void
  onLock: () => void
}

const VIEW_ORDER: ViewValue[] = ['feed', 'pipeline', 'applications', 'activity', 'settings']

function toggleTheme() {
  viewTransition(() => {
    const element = document.documentElement
    const light = !element.classList.contains('light')
    element.classList.remove('dark', 'light')
    element.classList.add(light ? 'light' : 'dark')
    try {
      localStorage.setItem('jobscope-theme', light ? 'light' : 'dark')
    } catch {
      // The theme still applies for this tab.
    }
  })
}

export function ShellV2({ data, state, onStateChange, onLock }: ShellV2Props) {
  const [commandOpen, setCommandOpen] = useState(false)
  const mobileReader = useMediaQuery('(max-width: 1023px)')
  const view = activeView(state)
  const selectedJob = useMemo(
    () => data.rows.find((row) => row.id === state.job) ?? null,
    [data.rows, state.job],
  )
  const selectedApplication = useMemo(
    () =>
      state.job
        ? (data.applications ?? []).find((application) => application.job_id === state.job) ?? null
        : null,
    [data.applications, state.job],
  )
  const searchedData = useMemo(() => filterData(data, state.q), [data, state.q])
  const feed = useMemo(() => buildFeed(data, state), [data, state])
  const board = useMemo(() => buildBoard(searchedData), [searchedData])
  const timeline = useMemo(() => buildTimeline(searchedData), [searchedData])
  const navigate = (next: ViewValue) => onStateChange({ view: next, job: undefined })
  const open = (jobId: string) => onStateChange({ job: jobId })
  const close = () => onStateChange({ job: undefined }, { replace: true })
  const refresh = useCallback(() => void scanNewMail(), [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setCommandOpen((open) => !open)
        return
      }
      const target = event.target
      const typing =
        target instanceof HTMLElement &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '/') {
        event.preventDefault()
        document.querySelector<HTMLInputElement>('input[type="search"]')?.focus()
        return
      }
      if (event.key === 'Escape' && state.job) {
        close()
        return
      }
      if (event.key >= '1' && event.key <= '5') {
        const next = VIEW_ORDER[Number(event.key) - 1]
        if (next) navigate(next)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <>
      <AppShell
        active={view}
        onNavigate={navigate}
        search={state.q}
        onSearch={(query) => onStateChange({ q: query }, { replace: true })}
        onOpenCommand={() => setCommandOpen(true)}
        onRefresh={refresh}
        onToggleTheme={toggleTheme}
        onLock={onLock}
      >
        {view === 'feed' ? (
          <div className="mx-auto grid h-full min-h-0 w-full max-w-[1600px] grid-cols-1 pb-16 sm:pb-0 lg:grid-cols-[minmax(500px,1fr)_minmax(500px,1fr)]">
            <FeedView
              model={feed}
              state={state}
              selectedId={state.job}
              onSelect={open}
              onStateChange={onStateChange}
            />
            <aside
              className="hidden min-h-0 flex-col border-r border-line bg-bg2 lg:flex"
              aria-label="Role reader"
            >
              {selectedJob ? (
                <RoleReader
                  job={selectedJob}
                  application={selectedApplication}
                  allRows={data.rows}
                  onOpen={open}
                  onClose={close}
                />
              ) : selectedApplication ? (
                <ApplicationReader app={selectedApplication} onClose={close} />
              ) : (
                <PipelinePreview
                  applications={data.applications ?? []}
                  onOpenPipeline={() => navigate('pipeline')}
                />
              )}
            </aside>
          </div>
        ) : view === 'pipeline' ? (
          <div className="px-3 pb-20 pt-4 sm:px-5 sm:pb-6 lg:px-7">
            <PipelineView applications={searchedData.applications ?? []} onOpen={open} />
          </div>
        ) : view === 'applications' ? (
          <div className="h-full min-h-0 pb-16 sm:pb-0">
            <Board columns={board} onOpen={open} />
          </div>
        ) : view === 'activity' ? (
          <div className="h-full min-h-0 pb-16 sm:pb-0">
            <Timeline timeline={timeline} onOpen={open} />
          </div>
        ) : (
          <div className="min-h-full pb-16 sm:pb-0">
            <Settings
              profile={data.profile}
              generated={data.generated}
              total={data.total}
              onLock={onLock}
            />
          </div>
        )}
      </AppShell>

      <CommandPalette
        key={commandOpen ? 'open' : 'closed'}
        open={commandOpen}
        onOpenChange={setCommandOpen}
        rows={data.rows}
        onNavigate={navigate}
        onOpenJob={open}
        onRefresh={refresh}
        onToggleTheme={toggleTheme}
        onLock={onLock}
      />

      <JobDrawer
        job={selectedJob}
        application={selectedApplication}
        allRows={data.rows}
        onOpen={open}
        onClose={close}
        enabled={view !== 'feed' || mobileReader}
      />
      <Toaster position="bottom-right" />
    </>
  )
}
