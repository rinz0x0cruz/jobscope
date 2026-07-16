import type {
  DashboardData,
  JobReview,
  JobRow,
  MonitoredCompany,
  MonitorStatus,
  ReviewState,
} from './schema'
import { localServeToken } from './outreach'

export const MONITORING_QUEUE_KEY = 'jobscope-monitoring-actions'
export const MONITORING_QUEUE_EVENT = 'jobscope:monitoring-queue'

export type MonitoringAction =
  | { type: 'monitor.upsert'; company: string; careers_url?: string; provider?: string; slug?: string; status?: MonitorStatus; job_id?: string }
  | { type: 'monitor.status'; monitor_id: string; status: MonitorStatus }
  | { type: 'monitor.scan'; monitor_id: string }
  | { type: 'review.set'; job_id: string; state: ReviewState }

export interface MonitoringActionResult {
  ok: boolean
  mode: 'local' | 'queued'
  error?: string
  companies?: MonitoredCompany[]
  reviews?: JobReview[]
  rows?: JobRow[]
  scans?: Array<{
    ok: boolean
    company: string
    matched?: number
    error?: string
    contact_status?: string
    recruiter_count?: number
    recruiter?: import('./schema').CompanyContact | null
    contact_error?: string
  }>
  queued: number
}

export interface CompanyResolution {
  ok: boolean
  error?: string
  company: string
  status: 'resolved' | 'unresolved' | 'unsupported'
  provider: string
  slug: string
  careers_url: string
  detail: string
  count: number
  matched: number
  results: Array<{ id: string; title: string; location: string; url: string; score: number; tier: string; rationale: string }>
}

function api(path: string): string {
  return `${location.origin}/${path}`
}

function actionKey(action: MonitoringAction): string {
  if (action.type === 'review.set') return `review:${action.job_id}`
  if (action.type === 'monitor.upsert') return `monitor-company:${action.company.trim().toLowerCase()}`
  return `monitor:${action.monitor_id}:${action.type}`
}

export function collapseMonitoringActions(actions: MonitoringAction[]): MonitoringAction[] {
  const collapsed = new Map<string, MonitoringAction>()
  for (const action of actions) collapsed.set(actionKey(action), action)
  return [...collapsed.values()]
}

export function queuedMonitoringActions(): MonitoringAction[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(MONITORING_QUEUE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed as MonitoringAction[] : []
  } catch {
    return []
  }
}

function writeQueue(actions: MonitoringAction[]): void {
  const collapsed = collapseMonitoringActions(actions)
  localStorage.setItem(MONITORING_QUEUE_KEY, JSON.stringify(collapsed))
  window.dispatchEvent(new CustomEvent(MONITORING_QUEUE_EVENT, { detail: collapsed.length }))
}

export function clearMonitoringQueue(): void {
  try {
    localStorage.removeItem(MONITORING_QUEUE_KEY)
    window.dispatchEvent(new CustomEvent(MONITORING_QUEUE_EVENT, { detail: 0 }))
  } catch {
    // A private browser can still use direct local actions.
  }
}

export function acknowledgeMonitoringActions(synced: MonitoringAction[]): void {
  const syncedByKey = new Map(
    collapseMonitoringActions(synced).map((action) => [actionKey(action), JSON.stringify(action)]),
  )
  const remaining = collapseMonitoringActions(queuedMonitoringActions()).filter((action) => {
    const serialized = syncedByKey.get(actionKey(action))
    return serialized === undefined || serialized !== JSON.stringify(action)
  })
  if (remaining.length) writeQueue(remaining)
  else clearMonitoringQueue()
}

export async function submitMonitoringActions(actions: MonitoringAction[]): Promise<MonitoringActionResult> {
  const collapsed = collapseMonitoringActions(actions)
  const token = await localServeToken()
  if (!token) {
    const queued = collapseMonitoringActions([...queuedMonitoringActions(), ...collapsed])
    writeQueue(queued)
    return { ok: true, mode: 'queued', queued: queued.length }
  }
  const response = await fetch(api('api/monitoring/actions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
    body: JSON.stringify({ actions: collapsed }),
  })
  const payload = await response.json() as Omit<MonitoringActionResult, 'mode' | 'queued'>
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `monitoring action failed (${response.status})`)
  }
  return { ...payload, mode: 'local', queued: queuedMonitoringActions().length }
}

export async function resolveCompany(
  company: string,
  careersUrl = '',
): Promise<CompanyResolution | null> {
  const token = await localServeToken()
  if (!token) return null
  const response = await fetch(api('api/companies/resolve'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
    body: JSON.stringify({ company, careers_url: careersUrl }),
  })
  const payload = await response.json() as CompanyResolution
  if (!response.ok) throw new Error(payload.error || `company resolution failed (${response.status})`)
  return payload
}

function queuedCompany(action: Extract<MonitoringAction, { type: 'monitor.upsert' }>): MonitoredCompany {
  const key = action.company.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return {
    id: `queued:${key}`,
    company: action.company.trim(),
    provider: action.provider || '',
    slug: action.slug || '',
    careers_url: action.careers_url || '',
    status: action.status || 'active',
    resolution_status: action.provider && action.slug ? 'resolved' : 'unresolved',
    added_from: ['user'],
    checked_at: '',
    last_success_at: '',
    health_status: '',
    health_detail: 'Queued for sync',
    board_count: 0,
    open_matches: 0,
    pending_count: 0,
    saved_count: 0,
    contact_domain: '',
    contacts_checked_at: '',
    recruiter_count: 0,
    recruiter: null,
  }
}

export function projectMonitoringActions(data: DashboardData, actions: MonitoringAction[]): DashboardData {
  let companies = [...data.companies]
  let reviews = [...data.reviews]
  for (const action of collapseMonitoringActions(actions)) {
    if (action.type === 'review.set') {
      const existing = reviews.find((review) => review.job_id === action.job_id)
      reviews = existing
        ? reviews.map((review) => review.job_id === action.job_id ? {
            ...review,
            state: action.state,
            reviewed_at: action.state === 'pending' ? '' : new Date().toISOString(),
          } : review)
        : [...reviews, {
            job_id: action.job_id,
            state: action.state,
            origins: ['discovery'],
            monitor_ids: [],
            first_seen: new Date().toISOString(),
            reviewed_at: action.state === 'pending' ? '' : new Date().toISOString(),
          }]
    } else if (action.type === 'monitor.status') {
      companies = companies.map((company) => company.id === action.monitor_id
        ? { ...company, status: action.status }
        : company)
    } else if (action.type === 'monitor.upsert') {
      const match = companies.find((company) => company.company.toLowerCase() === action.company.trim().toLowerCase())
      companies = match
        ? companies.map((company) => company.id === match.id ? {
            ...company,
            careers_url: action.careers_url || company.careers_url,
            provider: action.provider || company.provider,
            slug: action.slug || company.slug,
            status: action.status || 'active',
          } : company)
        : [...companies, queuedCompany(action)]
      if (action.job_id) {
        const monitor = companies.find((company) => company.company.toLowerCase() === action.company.trim().toLowerCase())
        reviews = reviews.map((review) => review.job_id === action.job_id ? {
          ...review,
          origins: review.origins.includes('monitored') ? review.origins : [...review.origins, 'monitored'],
          monitor_ids: monitor && !review.monitor_ids.includes(monitor.id)
            ? [...review.monitor_ids, monitor.id]
            : review.monitor_ids,
        } : review)
      }
    }
  }
  return { ...data, companies, reviews }
}