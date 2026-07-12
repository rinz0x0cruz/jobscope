// Client for the local `jobscope serve` outreach endpoint. On the public static
// site these calls 404 (no backend), so the drawer panel simply never appears.

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

// Probe the local serve API once; resolves to the CSRF token, or null on the
// public site (where /api/token does not exist).
let tokenProbe: Promise<string | null> | null = null
export function localServeToken(): Promise<string | null> {
  if (!tokenProbe) {
    tokenProbe = fetch(api('api/token'), { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => (j && typeof j.token === 'string' ? j.token : null))
      .catch(() => null)
  }
  return tokenProbe
}

export async function outreachPreview(jobId: string, token: string, to?: string, followup?: boolean): Promise<OutreachPreview> {
  const r = await fetch(api('api/outreach'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
    body: JSON.stringify({ job_id: jobId, ...(to ? { to } : {}), ...(followup ? { followup: true } : {}) }),
  })
  return (await r.json()) as OutreachPreview
}

export async function outreachSend(
  jobId: string,
  token: string,
  payload: { to: string; subject: string; body: string; force?: boolean },
): Promise<OutreachSendResult> {
  const r = await fetch(api('api/outreach'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
    body: JSON.stringify({ job_id: jobId, send: true, ...payload }),
  })
  return (await r.json()) as OutreachSendResult
}

// Free-text company search: resolve the employer's domain, discover HR contacts,
// and draft a résumé-attached note. Local `serve` only (the public site 404s).
export async function companyOutreachPreview(
  company: string,
  token: string,
  opts?: { url?: string; to?: string },
): Promise<CompanyOutreach> {
  const r = await fetch(api('api/company-outreach'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
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
  const r = await fetch(api('api/company-outreach'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
    body: JSON.stringify({ company, send: true, ...payload }),
  })
  return (await r.json()) as OutreachSendResult
}
