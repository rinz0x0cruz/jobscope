import type { DashboardData, JobReview, JobRow, MonitoredCompany } from './schema'
import { daysSince } from './pipeline'

export interface CompanyItem extends MonitoredCompany {
  pendingJobs: JobRow[]
  savedJobs: JobRow[]
}

export interface CompaniesModel {
  items: CompanyItem[]
  active: number
  paused: number
  needsSetup: number
}

export function buildCompanies(data: DashboardData, query = ''): CompaniesModel {
  const needle = query.trim().toLowerCase()
  const rows = new Map(data.rows.map((row) => [row.id, row]))
  const reviewsByMonitor = new Map<string, JobReview[]>()
  for (const review of data.reviews) {
    for (const monitorId of review.monitor_ids) {
      const bucket = reviewsByMonitor.get(monitorId) ?? []
      bucket.push(review)
      reviewsByMonitor.set(monitorId, bucket)
    }
  }
  const mapJobs = (reviews: JobReview[], state: 'pending' | 'saved') => reviews
    .filter((review) => review.state === state)
    .map((review) => rows.get(review.job_id))
    .filter((row): row is JobRow => row !== undefined)
    .sort((left, right) => right.score - left.score)

  const items = data.companies
    .filter((company) => !needle || [company.company, company.provider, company.slug]
      .some((value) => value.toLowerCase().includes(needle)))
    .map<CompanyItem>((company) => {
      const reviews = reviewsByMonitor.get(company.id) ?? []
      const pendingJobs = mapJobs(reviews, 'pending')
      const savedJobs = mapJobs(reviews, 'saved')
      return {
        ...company,
        pending_count: reviews.filter((review) => review.state === 'pending').length,
        saved_count: reviews.filter((review) => review.state === 'saved').length,
        pendingJobs,
        savedJobs,
      }
    })
    .sort((left, right) => left.company.localeCompare(right.company))

  return {
    items,
    active: data.companies.filter((company) => company.status === 'active').length,
    paused: data.companies.filter((company) => company.status === 'paused').length,
    needsSetup: data.companies.filter((company) => company.resolution_status !== 'resolved').length,
  }
}

export function monitorCheckAge(checkedAt: string, now = Date.now()): string {
  const age = daysSince(checkedAt, now)
  if (age === null) return 'not yet'
  if (age <= 0) return 'today'
  if (age === 1) return 'yesterday'
  return `${age}d ago`
}