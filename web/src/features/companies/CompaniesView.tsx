import { useState } from 'react'
import { ArrowLeft, ArrowRight, Building2, ExternalLink, Loader2, Mail, Pause, Play, RefreshCw, Settings2, Trash2 } from 'lucide-react'
import { monitorCheckAge, type CompaniesModel, type CompanyItem } from '@/lib/companies'
import type { CompanyFilter } from '@/lib/urlState'
import type { CompanyResolution, MonitoringAction } from '@/lib/companyActions'

export interface CompaniesViewProps {
  model: CompaniesModel
  filter: CompanyFilter
  selectedId?: string
  onFilter: (filter: CompanyFilter) => void
  onSelect: (companyId?: string) => void
  onOpenJob: (jobId: string) => void
  onResolve: (company: string, careersUrl?: string) => Promise<CompanyResolution | null>
  onActions: (actions: MonitoringAction[]) => Promise<void>
}

const FILTERS: Array<{ value: CompanyFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'setup', label: 'Needs setup' },
]

export function CompaniesView({ model, filter, selectedId, onFilter, onSelect, onOpenJob, onResolve, onActions }: CompaniesViewProps) {
  const [company, setCompany] = useState('')
  const [careersUrl, setCareersUrl] = useState('')
  const [resolving, setResolving] = useState(false)
  const [resolution, setResolution] = useState<CompanyResolution | null>(null)
  const editPortal = (item: CompanyItem) => {
    setCompany(item.company)
    setCareersUrl(item.careers_url)
    setResolution(null)
    onSelect(undefined)
  }
  const visible = model.items.filter((company) => {
    if (filter === 'all') return company.status !== 'removed'
    if (filter === 'setup') return company.resolution_status !== 'resolved'
    return company.status === filter
  })
  const selected = model.items.find((company) => company.id === selectedId) ?? null
  return (
    <section className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col border-x border-line bg-panel">
      <header className="shrink-0 border-b border-line px-5 py-5 sm:px-7">
        <p className="text-[10px] font-semibold uppercase text-ink-3">Companies</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div><h2 className="text-xl font-semibold text-ink">Monitored career portals</h2><p className="mt-1 text-[13px] text-ink-3">Follow official sources and review only relevant openings.</p></div>
          <div className="flex gap-4 text-right"><Metric label="Active" value={model.active} /><Metric label="Paused" value={model.paused} /><Metric label="Setup" value={model.needsSetup} /></div>
        </div>
      </header>
      <form
        className="grid shrink-0 gap-2 border-b border-line px-4 py-3 sm:grid-cols-[minmax(10rem,.7fr)_minmax(14rem,1fr)_auto] sm:px-7"
        onSubmit={(event) => {
          event.preventDefault()
          if (!company.trim()) return
          setResolving(true)
          void onResolve(company.trim(), careersUrl.trim())
            .then((result) => {
              if (result) setResolution(result)
              else return onActions([{ type: 'monitor.upsert', company: company.trim(), careers_url: careersUrl.trim() }])
            })
            .finally(() => setResolving(false))
        }}
      >
        <input value={company} onChange={(event) => setCompany(event.target.value)} aria-label="Company name" placeholder="Company name" className="h-9 rounded-md border border-line bg-inset px-3 text-[13px] text-ink outline-none focus:border-line-strong" />
        <input value={careersUrl} onChange={(event) => setCareersUrl(event.target.value)} aria-label="Careers portal URL" placeholder="Official careers URL (optional)" className="h-9 rounded-md border border-line bg-inset px-3 text-[13px] text-ink outline-none focus:border-line-strong" />
        <button type="submit" disabled={resolving || !company.trim()} className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand px-4 text-[12px] font-semibold text-white disabled:opacity-50">{resolving ? <Loader2 size={14} className="animate-spin" /> : <Building2 size={14} />} Find portal</button>
      </form>
      {resolution && <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line bg-inset/40 px-4 py-3 text-[12px] sm:px-7"><span><strong className="text-ink">{resolution.company}</strong> · {resolution.status === 'resolved' ? `${resolution.provider}/${resolution.slug} · ${resolution.count} openings · ${resolution.matched} matches` : resolution.detail || resolution.status}</span><div className="flex gap-2"><button type="button" onClick={() => { setResolution(null); void onActions([{ type: 'monitor.upsert', company: resolution.company, careers_url: resolution.careers_url, provider: resolution.provider, slug: resolution.slug }]) }} className="h-8 rounded-md border border-brand px-3 text-[11px] font-medium text-brand">Monitor company</button><button type="button" onClick={() => setResolution(null)} className="h-8 px-2 text-[11px] text-ink-3">Cancel</button></div></div>}
      <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-4 py-2 [scrollbar-width:none] sm:px-7 [&::-webkit-scrollbar]:hidden">
        {FILTERS.map((item) => <button key={item.value} type="button" aria-pressed={filter === item.value} onClick={() => onFilter(item.value)} className={`h-8 shrink-0 rounded-full border px-3 text-[11px] font-medium ${filter === item.value ? 'border-brand bg-brand-weak text-brand' : 'border-line text-ink-2'}`}>{item.label}</button>)}
      </div>
      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(340px,.78fr)_minmax(0,1.22fr)]">
        <div className={`${selected ? 'hidden lg:block' : 'block'} min-h-0 overflow-auto border-r border-line`}>
          {visible.length ? <ul>{visible.map((company) => <CompanyRow key={company.id} company={company} selected={company.id === selectedId} onSelect={() => onSelect(company.id)} />)}</ul> : <Empty />}
        </div>
        <div className={`${selected ? 'block' : 'hidden lg:block'} min-h-0 overflow-auto`}>
          {selected ? <CompanyDetail company={selected} onBack={() => onSelect(undefined)} onEdit={() => editPortal(selected)} onOpenJob={onOpenJob} onActions={onActions} /> : <NoSelection />}
        </div>
      </div>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><span className="block text-[9px] uppercase text-ink-3">{label}</span><strong className="font-mono text-lg text-ink">{value}</strong></div>
}

function CompanyRow({ company, selected, onSelect }: { company: CompanyItem; selected: boolean; onSelect: () => void }) {
  return <li className="border-b border-line"><button type="button" onClick={onSelect} aria-current={selected ? 'true' : undefined} className={`group grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-5 py-3 text-left outline-none hover:bg-inset/60 focus-visible:bg-inset sm:px-6 ${selected ? 'bg-brand-weak shadow-[inset_3px_0_var(--brand-coral)]' : ''}`}><span className="min-w-0"><span className="block truncate text-[14px] font-semibold text-ink">{company.company}</span><span className="mt-0.5 block truncate text-[11px] text-ink-3">{company.resolution_status === 'resolved' ? `${company.provider} · checked ${monitorCheckAge(company.checked_at)}` : 'Career portal needs setup'}</span><span className="mt-1 block text-[11px] text-ink-2">{company.pending_count} pending · {company.saved_count} saved</span></span><ArrowRight size={14} className="text-ink-3 transition-transform group-hover:translate-x-0.5" aria-hidden="true" /></button></li>
}

function CompanyDetail({ company, onBack, onEdit, onOpenJob, onActions }: { company: CompanyItem; onBack: () => void; onEdit: () => void; onOpenJob: (id: string) => void; onActions: (actions: MonitoringAction[]) => Promise<void> }) {
  const queued = company.id.startsWith('queued:')
  return (
    <div>
      <header className="border-b border-line px-5 py-5 sm:px-7">
        <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1 text-[12px] text-ink-3 lg:hidden">
          <ArrowLeft size={14} /> Companies
        </button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold text-ink">{company.company}</h3>
            <p className="mt-1 text-[12px] text-ink-3">
              {company.provider && company.slug ? `${company.provider}/${company.slug}` : company.resolution_status}
            </p>
          </div>
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${company.health_status === 'ok' ? 'bg-[color-mix(in_srgb,var(--strong)_14%,transparent)] text-strong' : 'bg-inset text-ink-3'}`}>
            {company.health_status || 'not checked'}
          </span>
        </div>
      </header>

      <div className="grid grid-cols-4 border-b border-line text-center">
        <MetricCell label="Board" value={company.board_count} />
        <MetricCell label="Open" value={company.open_matches} />
        <MetricCell label="Pending" value={company.pending_count} />
        <MetricCell label="Saved" value={company.saved_count} />
      </div>

      <section className="border-b border-line bg-inset/35 px-5 py-4 sm:px-7" aria-label="Recruiter contacts">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase text-ink-3">Preferred recruiter</p>
            {company.recruiter ? (
              <>
                <a
                  href={`mailto:${company.recruiter.email}`}
                  className="mt-1 inline-flex max-w-full items-center gap-1.5 text-[13px] font-semibold text-brand hover:underline"
                >
                  <Mail size={14} aria-hidden="true" />
                  <span className="truncate">{company.recruiter.email}</span>
                </a>
                <p className="mt-1 text-[11px] text-ink-3">
                  {company.recruiter.note || company.recruiter.source} · {company.recruiter.confidence} confidence
                </p>
              </>
            ) : (
              <p className="mt-1 text-[12px] text-ink-3">No verified recruiter yet. Run a targeted scan.</p>
            )}
          </div>
          <div className="text-right text-[10px] text-ink-3">
            <p>{company.recruiter_count} candidate{company.recruiter_count === 1 ? '' : 's'}</p>
            {company.contacts_checked_at && <p>checked {monitorCheckAge(company.contacts_checked_at)}</p>}
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2 border-b border-line px-5 py-3 sm:px-7">
        <button
          disabled={queued}
          onClick={() => void onActions([{ type: 'monitor.scan', monitor_id: company.id }])}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-brand px-3 text-[11px] font-medium text-brand disabled:opacity-40"
        >
          <RefreshCw size={13} /> Scan jobs + recruiter
        </button>
        <button
          disabled={queued}
          onClick={() => void onActions([{ type: 'monitor.status', monitor_id: company.id, status: company.status === 'paused' ? 'active' : 'paused' }])}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-[11px] text-ink-2 disabled:opacity-40"
        >
          {company.status === 'paused' ? <Play size={13} /> : <Pause size={13} />}
          {company.status === 'paused' ? 'Resume' : 'Pause'}
        </button>
        <button type="button" onClick={onEdit} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-[11px] text-ink-2">
          <Settings2 size={13} /> Edit portal
        </button>
        <button
          disabled={queued}
          onClick={() => { onBack(); void onActions([{ type: 'monitor.status', monitor_id: company.id, status: 'removed' }]) }}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-[11px] text-hot disabled:opacity-40"
        >
          <Trash2 size={13} /> Remove
        </button>
        {company.careers_url && (
          <a href={company.careers_url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 px-2 text-[11px] text-brand">
            Open careers <ExternalLink size={13} />
          </a>
        )}
      </div>

      <JobSection title="Pending review" jobs={company.pendingJobs} onOpen={onOpenJob} />
      <JobSection title="Saved roles" jobs={company.savedJobs} onOpen={onOpenJob} />
      {company.health_detail && <p className="border-t border-line px-5 py-3 text-[12px] text-hot sm:px-7">{company.health_detail}</p>}
    </div>
  )
}

function MetricCell({ label, value }: { label: string; value: number }) { return <div className="border-r border-line py-3 last:border-r-0"><span className="block text-[9px] uppercase text-ink-3">{label}</span><strong className="font-mono text-lg text-ink">{value}</strong></div> }
function JobSection({ title, jobs, onOpen }: { title: string; jobs: CompanyItem['pendingJobs']; onOpen: (id: string) => void }) { return <section><header className="flex items-center justify-between border-b border-line bg-inset px-5 py-2 sm:px-7"><h4 className="text-[10px] font-semibold uppercase text-ink-3">{title}</h4><span className="font-mono text-[11px] text-ink-3">{jobs.length}</span></header>{jobs.length ? <ul>{jobs.map((job) => <li key={job.id} className="border-b border-line"><button type="button" onClick={() => onOpen(job.id)} className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left hover:bg-inset/60 sm:px-7"><span className="min-w-0"><span className="block truncate text-[13px] font-medium text-ink">{job.title}</span><span className="text-[11px] text-ink-3">{job.location || 'Location unavailable'}</span></span><strong className="font-mono text-[13px] text-ink">{Math.round(job.score)}</strong></button></li>)}</ul> : <p className="px-5 py-6 text-[12px] text-ink-3 sm:px-7">No {title.toLowerCase()}.</p>}</section> }
function Empty() { return <div className="flex h-full flex-col items-center justify-center px-6 text-center"><Building2 size={28} className="text-ink-3" /><p className="mt-3 text-[14px] font-medium text-ink">No companies in this view</p></div> }
function NoSelection() { return <div className="flex h-full flex-col items-center justify-center px-6 text-center"><Building2 size={28} className="text-ink-3" /><p className="mt-3 text-[14px] font-medium text-ink">Select a monitored company</p><p className="mt-1 text-[12px] text-ink-3">Inspect source health and its review queue.</p></div> }