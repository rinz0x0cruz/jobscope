import type { DashboardData, JobReview, JobRow, MonitoredCompany } from './schema'
import { daysSince } from './pipeline'

export interface CompanyItem extends MonitoredCompany {
  pendingJobs: JobRow[]
  savedJobs: JobRow[]
  collectedRoleCount: number
  applicationCount: number
}

export interface CompaniesModel {
  items: CompanyItem[]
  allItems: CompanyItem[]
  active: number
  paused: number
  needsSetup: number
}

export function companyNameKey(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

export function buildCompanies(data: DashboardData, query = ''): CompaniesModel {
  const needle = query.trim().toLowerCase()
  const rows = new Map(data.rows.map((row) => [row.id, row]))
  const rolesByCompany = new Map<string, number>()
  const applicationsByCompany = new Map<string, number>()
  for (const row of data.rows) {
    const key = companyNameKey(row.company)
    if (key) rolesByCompany.set(key, (rolesByCompany.get(key) ?? 0) + 1)
  }
  for (const application of data.applications ?? []) {
    const key = companyNameKey(application.company)
    if (key) applicationsByCompany.set(key, (applicationsByCompany.get(key) ?? 0) + 1)
  }
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

  const allItems = data.companies
    .map<CompanyItem>((company) => {
      const reviews = reviewsByMonitor.get(company.id) ?? []
      const pendingJobs = mapJobs(reviews, 'pending')
      const savedJobs = mapJobs(reviews, 'saved')
      const companyKey = companyNameKey(company.company)
      return {
        ...company,
        pending_count: reviews.filter((review) => review.state === 'pending').length,
        saved_count: reviews.filter((review) => review.state === 'saved').length,
        pendingJobs,
        savedJobs,
        collectedRoleCount: rolesByCompany.get(companyKey) ?? 0,
        applicationCount: applicationsByCompany.get(companyKey) ?? 0,
      }
    })
    .sort((left, right) => left.company.localeCompare(right.company))
  const items = allItems.filter((company) => !needle || [
    company.company, company.provider, company.slug,
  ].some((value) => value.toLowerCase().includes(needle)))

  return {
    items,
    allItems,
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