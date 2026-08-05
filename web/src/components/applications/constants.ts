import type { Application } from '@/lib/schema'

// Canonical application status order — mirrors jobscope/core/model.py STATUSES.
export const STATUS_ORDER = [
  'new',
  'prepared',
  'applied',
  'interview',
  'rejected',
  'offer',
  'skipped',
] as const

export type Status = (typeof STATUS_ORDER)[number]

// Human labels (mirrors render.py APP_STATUS_LABEL).
export const STATUS_LABEL: Record<string, string> = {
  new: 'New',
  prepared: 'Prepared',
  applied: 'Applied',
  interview: 'Interview',
  rejected: 'Rejected',
  offer: 'Offer',
  skipped: 'Skipped',
}

// Status accent colors, all from theme tokens so both themes stay legible.
export const STATUS_COLOR: Record<string, string> = {
  new: 'var(--skip)',
  prepared: 'var(--accent)',
  applied: 'var(--good)',
  interview: 'var(--stretch)',
  rejected: 'var(--danger)',
  offer: 'var(--strong)',
  skipped: 'var(--mute)',
}

// Per-email signal colors (mirrors render.py SIGC).
export const SIGNAL_COLOR: Record<string, string> = {
  confirmation: 'var(--good)',
  recruiter: 'var(--mute)',
  assessment: 'var(--accent)',
  interview: 'var(--stretch)',
  offer: 'var(--strong)',
  rejection: 'var(--danger)',
  manual: 'var(--accent)',
  other: 'var(--mute)',
}

export function statusColor(status: string): string {
  return STATUS_COLOR[status] ?? 'var(--accent)'
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

export function signalColor(signal: string): string {
  return SIGNAL_COLOR[signal] ?? 'var(--mute)'
}

// Pipeline flow metrics — mirrors render.py pipeline():
// Applied -> {Interview, Rejected, No response} -> {Offer, Rejected, In process}.
export interface PipelineMetrics {
  submitted: number
  reachedIv: number
  offers: number
  rejBefore: number
  rejAfter: number
  noResp: number
  inProc: number
}

const PIPELINE_STATUSES = new Set(['applied', 'interview', 'offer', 'rejected'])

function reachedInterview(a: Application): boolean {
  return (
    a.status === 'interview' ||
    a.status === 'offer' ||
    (a.timeline ?? []).some((e) => e.signal === 'interview' || e.signal === 'assessment')
  )
}

export function pipelineMetrics(apps: Application[]): PipelineMetrics {
  const rel = apps.filter((a) => PIPELINE_STATUSES.has(a.status))
  let reachedIv = 0
  let offers = 0
  let rejBefore = 0
  let rejAfter = 0
  let noResp = 0
  let inProc = 0
  for (const a of rel) {
    const iv = reachedInterview(a)
    if (a.status === 'offer') {
      reachedIv += 1
      offers += 1
    } else if (a.status === 'rejected') {
      if (iv) {
        reachedIv += 1
        rejAfter += 1
      } else {
        rejBefore += 1
      }
    } else if (a.status === 'interview') {
      reachedIv += 1
      inProc += 1
    } else {
      noResp += 1
    }
  }
  return { submitted: rel.length, reachedIv, offers, rejBefore, rejAfter, noResp, inProc }
}

export function pct(n: number, total: number): number {
  return total ? Math.round((n / total) * 100) : 0
}
