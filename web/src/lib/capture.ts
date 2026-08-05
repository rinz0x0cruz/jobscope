import { controlPlaneFetch, localServeToken } from './outreach'

export interface CaptureResult {
  ok: boolean
  error?: string
  needs_text?: boolean
  job_id: string
  title: string
  company: string
  location: string
  url: string
  source: 'url' | 'text'
  score: number
  tier: string
  rationale: string
  duplicate_of: string
  warnings: string[]
  saved: boolean
  is_new?: boolean
}

export class CaptureError extends Error {
  needsText: boolean

  constructor(message: string, needsText = false) {
    super(message)
    this.name = 'CaptureError'
    this.needsText = needsText
  }
}

/** Preview one posting. Pass `save` only after the user has seen the parse. */
export async function captureRole(
  input: { url?: string; text?: string; save?: boolean },
): Promise<CaptureResult | null> {
  const token = await localServeToken()
  if (!token) return null
  const response = await controlPlaneFetch('api/capture', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  const payload = await response.json() as CaptureResult
  if (!response.ok) {
    throw new CaptureError(
      payload.error || `capture failed (${response.status})`,
      Boolean(payload.needs_text),
    )
  }
  return payload
}
