import { useCallback, useEffect, useMemo, useState } from 'react'
import { Toaster, toast } from 'sonner'
import { AppShell } from '@/app/AppShell'
import { Board } from '@/features/board'
import { FeedView } from '@/features/feed'
import { CompaniesView } from '@/features/companies'
import { PipelinePreview, PipelineView } from '@/features/pipeline'
import { Timeline } from '@/features/timeline'
import { Settings } from '@/features/settings'
import { CommandPalette } from '@/features/command'
import { ApplicationReader, JobDrawer, RoleReader } from '@/components/JobDrawer'
import { buildBoard } from '@/lib/board'
import { buildFeed } from '@/lib/feed'
import { buildCompanies } from '@/lib/companies'
import { buildTimeline } from '@/lib/timeline'
import { filterData } from '@/lib/viewFilter'
import { activeView, type SearchState, type ViewValue } from '@/lib/urlState'
import { scanNewMail, syncMonitoringQueue } from '@/lib/refresh'
import { viewTransition } from '@/ui'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import type { DashboardData } from '@/lib/schema'
import {
  MONITORING_QUEUE_EVENT,
  projectMonitoringActions,
  queuedMonitoringActions,
  resolveCompany,
  submitMonitoringActions,
  type MonitoringAction,
} from '@/lib/companyActions'

export interface ShellV2Props {
  data: DashboardData
  state: SearchState
  onStateChange: (patch: Partial<SearchState>, options?: { replace?: boolean }) => void
  onLock: () => void
}

const VIEW_ORDER: ViewValue[] = ['review', 'companies', 'pipeline', 'applications', 'activity', 'settings']

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
  const [pendingChanges, setPendingChanges] = useState(() => queuedMonitoringActions().length)
  const [workingData, setWorkingData] = useState(() =>
    projectMonitoringActions(data, queuedMonitoringActions()),
  )
  const mobileReader = useMediaQuery('(max-width: 1399px)')
  const view = activeView(state)
  const selectedJob = useMemo(
    () => workingData.rows.find((row) => row.id === state.job) ?? null,
    [workingData.rows, state.job],
  )
  const selectedApplication = useMemo(
    () =>
      state.job
        ? (workingData.applications ?? []).find((application) => application.job_id === state.job) ?? null
        : null,
    [workingData.applications, state.job],
  )
  const searchedData = useMemo(() => filterData(workingData, state.q), [workingData, state.q])
  const feed = useMemo(() => buildFeed(workingData, state), [workingData, state])
  const companies = useMemo(() => buildCompanies(workingData, state.q), [workingData, state.q])
  const board = useMemo(() => buildBoard(searchedData), [searchedData])
  const timeline = useMemo(() => buildTimeline(searchedData), [searchedData])
  const navigate = (next: ViewValue) => onStateChange({ view: next, job: undefined, company: undefined })
  const open = (jobId: string) => onStateChange({ job: jobId })
  const close = () => onStateChange({ job: undefined }, { replace: true })
  const refresh = useCallback(() => void scanNewMail(), [])
  const runMonitoringActions = async (actions: MonitoringAction[]) => {
    const previous = workingData
    setWorkingData((current) => projectMonitoringActions(current, actions))
    try {
      const result = await submitMonitoringActions(actions)
      if (result.mode === 'local' && result.companies && result.reviews) {
        setWorkingData((current) => ({
          ...current,
          rows: result.rows ?? current.rows,
          companies: result.companies ?? current.companies,
          reviews: result.reviews ?? current.reviews,
        }))
        const scan = result.scans?.[0]
        if (scan) {
          const recruiter = scan.recruiter?.email
          toast.success(`Scanned ${scan.company}`, {
            description: `${scan.matched ?? 0} matched role${scan.matched === 1 ? '' : 's'} · ${recruiter || 'no verified recruiter found'}`,
          })
        } else {
          toast.success('Changes saved locally')
        }
      } else {
        toast.success('Change queued', { description: 'Sync queued changes to update the encrypted dashboard.' })
      }
    } catch (error) {
      setWorkingData(previous)
      toast.error(error instanceof Error ? error.message : 'Could not apply change')
    }
  }

  useEffect(() => {
    const updateCount = () => setPendingChanges(queuedMonitoringActions().length)
    window.addEventListener(MONITORING_QUEUE_EVENT, updateCount)
    return () => window.removeEventListener(MONITORING_QUEUE_EVENT, updateCount)
  }, [])

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
      if (event.key >= '1' && event.key <= '6') {
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
        pendingChanges={pendingChanges}
        onSyncChanges={() => void syncMonitoringQueue()}
      >
        {view === 'review' ? (
          <div className="mx-auto grid h-full min-h-0 w-full max-w-[1600px] grid-cols-1 pb-16 lg:pb-0 min-[1400px]:grid-cols-[minmax(600px,1.08fr)_minmax(500px,.92fr)]">
            <FeedView
              model={feed}
              state={state}
              selectedId={state.job}
              onSelect={open}
              onStateChange={onStateChange}
              onReviewState={(jobId, reviewState) => void runMonitoringActions([
                { type: 'review.set', job_id: jobId, state: reviewState },
              ])}
              onMonitorCompany={(jobId, company, postingUrl) => void runMonitoringActions([
                { type: 'monitor.upsert', company, careers_url: postingUrl, job_id: jobId },
              ])}
            />
            <aside
              className="hidden min-h-0 flex-col border-r border-line bg-bg2 min-[1400px]:flex"
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
                  applications={workingData.applications ?? []}
                  onOpenPipeline={() => navigate('pipeline')}
                />
              )}
            </aside>
          </div>
        ) : view === 'companies' ? (
          <div className="h-full min-h-0 pb-16 lg:pb-0">
            <CompaniesView
              model={companies}
              filter={state.companyFilter}
              selectedId={state.company}
              onFilter={(companyFilter) => onStateChange({ companyFilter }, { replace: true })}
              onSelect={(company) => onStateChange({ company })}
              onOpenJob={open}
              onResolve={resolveCompany}
              onActions={(actions) => runMonitoringActions(actions)}
            />
          </div>
        ) : view === 'pipeline' ? (
          <div className="px-3 pb-20 pt-4 sm:px-5 lg:px-7 lg:pb-6">
            <PipelineView applications={searchedData.applications ?? []} onOpen={open} />
          </div>
        ) : view === 'applications' ? (
          <div className="h-full min-h-0 pb-16 lg:pb-0">
            <Board columns={board} onOpen={open} />
          </div>
        ) : view === 'activity' ? (
          <div className="h-full min-h-0 pb-16 lg:pb-0">
            <Timeline timeline={timeline} onOpen={open} />
          </div>
        ) : (
          <div className="min-h-full pb-16 lg:pb-0">
            <Settings
              profile={workingData.profile}
              generated={workingData.generated}
              total={workingData.total}
              onLock={onLock}
              onProfileChange={(profile) => setWorkingData((current) => ({ ...current, profile }))}
            />
          </div>
        )}
      </AppShell>

      <CommandPalette
        key={commandOpen ? 'open' : 'closed'}
        open={commandOpen}
        onOpenChange={setCommandOpen}
        rows={workingData.rows}
        onNavigate={navigate}
        onOpenJob={open}
        onRefresh={refresh}
        onToggleTheme={toggleTheme}
        onLock={onLock}
      />

      <JobDrawer
        job={selectedJob}
        application={selectedApplication}
        allRows={workingData.rows}
        onOpen={open}
        onClose={close}
        enabled={view !== 'review' || mobileReader}
      />
      <Toaster position="bottom-right" />
    </>
  )
}
