// Client for the local `jobscope serve` company-scout endpoint. On the public
// static site this 404s (no backend), so the Scout panel never appears.

import type { Tier } from '@/lib/schema'

const api = (path: string) => `${location.origin}/${path}`

export interface ScoutResult {
  title: string
  company: string
  location: string
  url: string
  remote: boolean
  score: number
  tier: Tier
  rationale: string
  saved: boolean
}

export interface ScoutResponse {
  ok: boolean
  error?: string
  needs_slug?: boolean
  company?: string
  provider?: string
  slug?: string
  count?: number
  matched?: number
  saved?: number
  results?: ScoutResult[]
}

// Fetch a company's ATS board (Greenhouse/Lever/Ashby) and rank its openings
// against the active profile. `save` upserts the matches into the pipeline.
export async function scoutCompany(
  company: string,
  token: string,
  opts?: { provider?: string; slug?: string; save?: boolean; limit?: number },
): Promise<ScoutResponse> {
  const r = await fetch(api('api/scout'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Refresh-Token': token },
    body: JSON.stringify({ company, ...opts }),
  })
  return (await r.json()) as ScoutResponse
}
