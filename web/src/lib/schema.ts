// Typed mirror of the Python data contract emitted by
// `jobscope dashboard --emit-json` (render.py: build_data / _job_record /
// _overview_data). Keep this 1:1 with the Python shapes.

export type Tier = 'Strong' | 'Good' | 'Stretch' | 'Skip'

export interface StockSummary {
  ticker?: string
  price?: number
  change_pct?: number
  market_cap?: string
  public?: boolean
}

export interface CompSummary {
  levels_fyi?: string
  levels_search?: string
  min?: number
  max?: number
  interval?: string
  currency?: string
  source?: string
  range?: string
}

export interface RedditSummary {
  sentiment?: string | null
  summary?: string | null
  count?: number
}

export interface NewsItem {
  title?: string
  link?: string
  published?: string
  source?: string
}

export interface EnrichSummary {
  stock?: StockSummary
  comp?: CompSummary
  reddit?: RedditSummary
  news?: NewsItem[]
  glassdoor?: Record<string, unknown>
}

export interface Contact {
  name?: string | null
  title?: string | null
  url?: string | null
}

export interface JobRow {
  id: string
  title: string
  company: string
  location: string
  remote: boolean
  remote_scope: string
  url: string
  source: string
  score: number
  tier: Tier
  base: string
  salary: string
  size: string
  funding: string
  country: string
  place: string
  industry: string | null
  rationale: string
  blocked: boolean
  posted: string | null
  first_seen: string
  status: string
  last_seen: string
  closed_at: string
  enrich: EnrichSummary
  brief: string
  contacts: Contact[]
}

export interface Overview {
  funnel: Record<string, number>
  gaps: [string, number][]
  considered: number
  targets: string[]
}

export interface DashboardData {
  generated: string
  total: number
  rows: JobRow[]
  overview: Overview
}

export const TIERS: Tier[] = ['Strong', 'Good', 'Stretch', 'Skip']

export const TIER_COLOR: Record<Tier, string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}
