// Client for the local `jobscope serve` outreach endpoint. Public/static origins
// never probe these routes, so local-only controls simply remain unavailable.

import { normalizeDashboardData, type DashboardData, type Profile } from '@/lib/schema'

export interface OutreachPreview {
  ok: boolean
  error?: string
  needs_address?: boolean
  to?: string
  source?: string
  confidence?: string
  note?: string
  subject?: string
  body?: string
  resume?: string
  company?: string
  title?: string
  already_at?: string
  blocked?: boolean
  sendable?: boolean
}

export interface OutreachSendResult {
  ok: boolean
  sent?: boolean
  to?: string
  error?: string
}

// A plausible HR/recruiting contact for a company search (deterministic).
export interface CompanyContact {
  email: string
  confidence: string // high | medium | low
  source: string // override | discovered | role_inbox
  note: string
}

export interface CompanyOutreach {
  ok: boolean
  error?: string
  needs_url?: boolean
  company?: string
  domain?: string
  candidates?: CompanyContact[]
  subject?: string
  body?: string
  resume?: string
  sendable?: boolean
}

const api = (path: string) => `${location.origin}/${path}`
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1'])
export const HOSTED_SESSION_EXPIRED_EVENT = 'jobscope:hosted-session-expired'

// Probe the control plane once on loopback or in the explicit hosted build.
let tokenProbe: Promise<string | null> | null = null
let dashboardProbe: Promise<DashboardData> | null = null

export function resetLocalServeToken(): void {
  tokenProbe = null
  dashboardProbe = null
}

function requireHostedSession(response: Response): Response {
  const contentType = response.headers?.get?.('Content-Type') || ''
  if (
    import.meta.env.VITE_JOBSCOPE_HOSTED === '1'
    && (response.redirected || response.type === 'opaqueredirect' || contentType.includes('text/html'))
  ) {
    resetLocalServeToken()
    window.dispatchEvent(new Event(HOSTED_SESSION_EXPIRED_EVENT))
    throw new Error('Private session expired. Sign in again.')
  }
  return response
}

export function localServeToken(): Promise<string | null> {
  const hostedBuild = import.meta.env.VITE_JOBSCOPE_HOSTED === '1'
  if (!hostedBuild && !LOOPBACK_HOSTS.has(location.hostname.toLowerCase())) {
    return Promise.resolve(null)
  }
  if (!tokenProbe) {
    tokenProbe = fetch(api('api/token'), { cache: 'no-store' })
      .then(requireHostedSession)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => (j && typeof j.token === 'string' ? j.token : null))
      .catch(() => null)
  }
  return tokenProbe
}

export async function controlPlaneFetch(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<Response> {
  const request = (currentToken: string) => {
    const headers = new Headers(init.headers)
    headers.set('X-Refresh-Token', currentToken)
    return fetch(api(path), { ...init, headers }).then(requireHostedSession)
  }
  const cachedToken = tokenProbe ? await tokenProbe : null
  const currentToken = cachedToken || token
  const response = await request(currentToken)
  if (response.status !== 403) return response
  resetLocalServeToken()
  const freshToken = await localServeToken()
  return freshToken && freshToken !== currentToken ? request(freshToken) : response
}

export async function outreachPreview(jobId: string, token: string, to?: string, followup?: boolean): Promise<OutreachPreview> {
  const r = await controlPlaneFetch('api/outreach', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, ...(to ? { to } : {}), ...(followup ? { followup: true } : {}) }),
  })
  return (await r.json()) as OutreachPreview
}

export async function outreachSend(
  jobId: string,
  token: string,
  payload: { to: string; subject: string; body: string; force?: boolean },
): Promise<OutreachSendResult> {
  const r = await controlPlaneFetch('api/outreach', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, send: true, ...payload }),
  })
  return (await r.json()) as OutreachSendResult
}

// Persist offer/interview fields on a tracked application. Local `serve` only
// (the public static site has no backend, so the offer editor stays hidden).
export interface OfferFields {
  interview_at?: string
  salary_offered?: string
  offer_accepted?: string
}

export interface ApplicationUpdateResult {
  ok: boolean
  error?: string
  updated?: { job_id: string; interview_at: string; salary_offered: string; offer_accepted: string }
}

export async function applicationUpdate(
  jobId: string,
  token: string,
  fields: OfferFields,
): Promise<ApplicationUpdateResult> {
  const r = await controlPlaneFetch('api/application/update', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, ...fields }),
  })
  return (await r.json()) as ApplicationUpdateResult
}

// Switch the active search profile (the one that drives `scan`). Local `serve`
// only; returns the freshly-active profile so the UI can update in place.
export interface ProfileUseResult {
  ok: boolean
  error?: string
  profile?: Profile
}

export interface ProfileUploadResult extends ProfileUseResult {
  profile_count?: number
  profile_limit?: number
}

export function localDashboard(token: string, refresh = false): Promise<DashboardData> {
  if (refresh) dashboardProbe = null
  if (!dashboardProbe) {
    dashboardProbe = controlPlaneFetch('api/dashboard', token, {
      cache: 'no-store',
    }).then(async (response) => {
      const result = await response.json() as { ok?: boolean; error?: string; data?: DashboardData }
      if (!response.ok || !result.ok || !result.data) {
        throw new Error(result.error || 'Could not load local dashboard')
      }
      return normalizeDashboardData(result.data)
    }).catch((error) => {
      dashboardProbe = null
      throw error
    })
  }
  return dashboardProbe
}

export interface ProfileIntentUpdate {
  search_terms: string[]
  locations: string[]
  remote: boolean
}

function fileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Could not read resume'))
    reader.onload = () => {
      const value = String(reader.result || '')
      resolve(value.includes(',') ? value.slice(value.indexOf(',') + 1) : value)
    }
    reader.readAsDataURL(file)
  })
}

export async function profileUse(name: string, token: string): Promise<ProfileUseResult> {
  const r = await controlPlaneFetch('api/profile/use', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return (await r.json()) as ProfileUseResult
}

export async function profileUpdate(
  name: string,
  token: string,
  intent: ProfileIntentUpdate,
): Promise<ProfileUseResult> {
  const r = await controlPlaneFetch('api/profile', token, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, ...intent }),
  })
  return (await r.json()) as ProfileUseResult
}

export async function profileReset(name: string, token: string): Promise<ProfileUseResult> {
  const r = await controlPlaneFetch('api/profile/reset', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return (await r.json()) as ProfileUseResult
}

export async function profileUpload(
  file: File,
  name: string,
  token: string,
): Promise<ProfileUploadResult> {
  const contentBase64 = await fileAsBase64(file)
  const r = await controlPlaneFetch('api/resume/upload', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      filename: file.name,
      content_base64: contentBase64,
    }),
  })
  return (await r.json()) as ProfileUploadResult
}

// Free-text company search: resolve the employer's domain, discover HR contacts,
// and draft a résumé-attached note. Local `serve` only (the public site 404s).
export async function companyOutreachPreview(
  company: string,
  token: string,
  opts?: { url?: string; to?: string },
): Promise<CompanyOutreach> {
  const r = await controlPlaneFetch('api/company-outreach', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      company,
      ...(opts?.url ? { url: opts.url } : {}),
      ...(opts?.to ? { to: opts.to } : {}),
    }),
  })
  return (await r.json()) as CompanyOutreach
}

export async function companyOutreachSend(
  company: string,
  token: string,
  payload: { to: string; subject: string; body: string; url?: string; force?: boolean },
): Promise<OutreachSendResult> {
  const r = await controlPlaneFetch('api/company-outreach', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company, send: true, ...payload }),
  })
  return (await r.json()) as OutreachSendResult
}
