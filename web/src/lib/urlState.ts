import { z } from 'zod'
import type { JobRow } from './schema'

export const TAB_VALUES = ['overview', 'applications', 'outreach', 'all', 'Strong', 'Good', 'Stretch', 'Skip'] as const
export type TabValue = (typeof TAB_VALUES)[number]
export const VIEW_VALUES = ['review', 'companies', 'pipeline', 'applications', 'activity', 'settings'] as const
export type ViewValue = (typeof VIEW_VALUES)[number]
export const URL_VIEW_VALUES = [...VIEW_VALUES, 'feed'] as const
export const REVIEW_BUCKET_VALUES = ['monitored', 'discovery', 'saved', 'dismissed'] as const
export type ReviewBucket = (typeof REVIEW_BUCKET_VALUES)[number]
export const COMPANY_FILTER_VALUES = ['all', 'active', 'known', 'paused', 'setup'] as const
export type CompanyFilter = (typeof COMPANY_FILTER_VALUES)[number]
export const FEED_SORT_VALUES = ['score', 'newest', 'company'] as const
export type FeedSort = (typeof FEED_SORT_VALUES)[number]
export const FEED_FLAG_VALUES = ['remote', 'salary', 'referral', 'fresh', 'hide-stale'] as const
export type FeedFlag = (typeof FEED_FLAG_VALUES)[number]
export const FEED_TIER_VALUES = ['Strong', 'Good', 'Stretch'] as const

// All view state lives in the URL (hash) search params -> shareable, back/forward,
// restorable. Every field has a `.catch` default so parsing a bad/absent URL never
// throws and simply falls back.
export const searchSchema = z.object({
  tab: z.enum(TAB_VALUES).catch('all'),
  view: z.enum(URL_VIEW_VALUES).optional(),
  reviewBucket: z.enum(REVIEW_BUCKET_VALUES).catch('monitored'),
  company: z.string().optional(),
  companyFilter: z.enum(COMPANY_FILTER_VALUES).catch('active'),
  sort: z.enum(FEED_SORT_VALUES).catch('score'),
  flags: z.array(z.enum(FEED_FLAG_VALUES)).catch([]),
  tiers: z.array(z.enum(FEED_TIER_VALUES)).catch([]),
  q: z.string().catch(''),
  resume: z.array(z.string()).catch([]),
  country: z.array(z.string()).catch([]),
  place: z.array(z.string()).catch([]),
  mode: z.array(z.string()).catch([]),
  funding: z.array(z.string()).catch([]),
  scope: z.array(z.string()).catch([]),
  group: z.boolean().catch(false),
  hideClosed: z.boolean().catch(true),
  job: z.string().optional(),
})

export type SearchState = z.infer<typeof searchSchema>

// Defaults matching each field's `.catch(...)` above. Fed to the router's
// stripSearchParams middleware so a view at defaults yields a clean URL (no
// tab=all&q=&resume=[]... noise); only changed filters appear in the hash.
export const SEARCH_DEFAULTS: Partial<SearchState> = {
  tab: 'all',
  sort: 'score',
  flags: [],
  tiers: [],
  reviewBucket: 'monitored',
  companyFilter: 'active',
  q: '',
  resume: [],
  country: [],
  place: [],
  mode: [],
  funding: [],
  scope: [],
  group: false,
  hideClosed: true,
}

export function activeView(state: SearchState): ViewValue {
  if (state.view === 'feed') return 'review'
  if (state.view) return state.view
  if (state.tab === 'applications' || state.tab === 'outreach') return 'applications'
  if (state.tab === 'overview') return 'pipeline'
  return 'review'
}

export type FacetKey = 'resume' | 'country' | 'place' | 'mode' | 'funding' | 'scope'

export interface FacetDef {
  key: FacetKey
  label: string
  get: (r: JobRow) => string
}

export const FACETS: FacetDef[] = [
  { key: 'resume', label: 'Resume', get: (r) => r.base },
  { key: 'country', label: 'Country', get: (r) => r.country },
  { key: 'place', label: 'Location', get: (r) => r.place },
  { key: 'mode', label: 'Work mode', get: (r) => (r.remote ? 'Remote' : 'On-site') },
  { key: 'funding', label: 'Funding', get: (r) => r.funding },
  { key: 'scope', label: 'Remote scope', get: (r) => (r.remote ? r.remote_scope || 'Anywhere' : '') },
]

export const FACET_KEYS: FacetKey[] = FACETS.map((f) => f.key)
