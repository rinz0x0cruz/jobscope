import { z } from 'zod'
import type { JobRow } from './schema'

export const TAB_VALUES = ['overview', 'applications', 'all', 'Strong', 'Good', 'Stretch', 'Skip'] as const
export type TabValue = (typeof TAB_VALUES)[number]

// All view state lives in the URL (hash) search params -> shareable, back/forward,
// restorable. Every field has a `.catch` default so parsing a bad/absent URL never
// throws and simply falls back.
export const searchSchema = z.object({
  tab: z.enum(TAB_VALUES).catch('all'),
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
