import type { DashboardData, JobReview, JobRow, Tier } from './schema'
import { FACETS, type FacetKey, type FeedFlag, type FeedSort, type ReviewBucket, type SearchState } from './urlState'
import { daysSince } from './pipeline'

export interface FeedItem {
  row: JobRow
  ageDays: number | null
  hasSalary: boolean
  hasReferral: boolean
  sourceNames: string[]
  preview: string
  review: JobReview
}

export interface FeedModel {
  items: FeedItem[]
  facetRows: JobRow[]
  total: number
  available: number
  buckets: Record<ReviewBucket, number>
}

function matchesQuery(row: JobRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    row.title,
    row.company,
    row.location,
    row.place,
    row.country,
    row.industry,
    row.rationale,
    row.brief,
    row.source,
    ...row.sources.map((source) => source.source),
  ].some((value) => (value || '').toLowerCase().includes(needle))
}

function matchesFacets(row: JobRow, state: SearchState): boolean {
  for (const facet of FACETS) {
    const selected = state[facet.key as FacetKey]
    if (!selected.length) continue
    const value = facet.get(row)
    if (!value || !selected.includes(value)) return false
  }
  return true
}

function matchesFlags(row: JobRow, flags: FeedFlag[], now: number): boolean {
  if (flags.includes('remote') && !row.remote) return false
  if (flags.includes('salary') && !row.salary.trim()) return false
  if (flags.includes('referral') && row.contacts.length === 0) return false
  if (flags.includes('fresh')) {
    const age = daysSince(row.first_seen, now)
    if (age === null || age < 0 || age >= 7) return false
  }
  if (flags.includes('hide-stale') && row.stale) return false
  return true
}

function legacyTier(tab: SearchState['tab']): Tier[] {
  return ['Strong', 'Good', 'Stretch', 'Skip'].includes(tab) ? [tab as Tier] : []
}

function compare(sort: FeedSort): (left: FeedItem, right: FeedItem) => number {
  if (sort === 'newest') {
    return (left, right) =>
      (right.row.first_seen || '').localeCompare(left.row.first_seen || '') ||
      right.row.score - left.row.score
  }
  if (sort === 'company') {
    return (left, right) =>
      left.row.company.localeCompare(right.row.company) || right.row.score - left.row.score
  }
  return (left, right) => right.row.score - left.row.score || left.row.company.localeCompare(right.row.company)
}

export function buildFeed(data: DashboardData, state: SearchState, now = Date.now()): FeedModel {
  const applicationIds = new Set((data.applications ?? []).map((application) => application.job_id))
  const reviewByJob = new Map(data.reviews.map((review) => [review.job_id, review]))
  const candidateRows = data.rows.filter(
    (row) => !applicationIds.has(row.id) && row.tier !== 'Skip' && row.status === 'open' && !row.closed_at,
  )
  const bucketOf = (review: JobReview): ReviewBucket => {
    if (review.state === 'saved') return 'saved'
    if (review.state === 'dismissed') return 'dismissed'
    return review.origins.includes('monitored') ? 'monitored' : 'discovery'
  }
  const buckets: Record<ReviewBucket, number> = { monitored: 0, discovery: 0, saved: 0, dismissed: 0 }
  for (const row of candidateRows) {
    const review = reviewByJob.get(row.id)
    if (review) buckets[bucketOf(review)] += 1
  }
  const availableRows = candidateRows.filter((row) => {
    const review = reviewByJob.get(row.id)
    return review ? bucketOf(review) === state.reviewBucket : false
  })
  const tiers = state.tiers.length ? state.tiers : legacyTier(state.tab)

  const items = availableRows
    .filter((row) => !tiers.length || tiers.includes(row.tier))
    .filter((row) => matchesQuery(row, state.q))
    .filter((row) => matchesFacets(row, state))
    .filter((row) => matchesFlags(row, state.flags, now))
    .map<FeedItem>((row) => {
      const review = reviewByJob.get(row.id)
      if (!review) throw new Error(`missing review for ${row.id}`)
      return {
        row,
        ageDays: daysSince(row.first_seen, now),
        hasSalary: Boolean(row.salary.trim()),
        hasReferral: row.contacts.length > 0,
        sourceNames: [...new Set(row.sources.map((source) => source.source).filter(Boolean))],
        preview: (row.rationale || row.brief || row.description || '').trim(),
        review,
      }
    })
    .sort(compare(state.sort))

  return { items, facetRows: availableRows, total: items.length, available: availableRows.length, buckets }
}
