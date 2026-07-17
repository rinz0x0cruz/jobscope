import type { DashboardData, JobReview, JobRow, MonitoredCompany } from './schema'
import { daysSince } from './pipeline'

export interface CompanyItem extends MonitoredCompany {
  pendingJobs: JobRow[]
  savedJobs: JobRow[]
  collectedJobs: JobRow[]
  collectedRoleCount: number
  applicationCount: number
}

export interface CompaniesModel {
  items: CompanyItem[]
  allItems: CompanyItem[]
  watching: number
  known: number
  paused: number
  needsSetup: number
}

const COMPANY_SUFFIXES = new Set([
  'ag', 'co', 'company', 'corp', 'corporation', 'gmbh', 'inc', 'incorporated',
  'limited', 'llc', 'ltd', 'plc', 'private', 'pvt', 'solutions', 'systems',
  'technologies', 'technology',
])

export function companyNameKey(value: string): string {
  const tokens = value.normalize('NFKC').toLowerCase().match(/[a-z0-9]+/g) ?? []
  while (tokens.length && COMPANY_SUFFIXES.has(tokens[tokens.length - 1])) tokens.pop()
  return tokens.join(' ')
}

export function buildCompanies(data: DashboardData, query = ''): CompaniesModel {
  const needle = query.trim().toLowerCase()
  const rows = new Map(data.rows.map((row) => [row.id, row]))
  const rolesByCompany = new Map<string, number>()
  const collectedJobsByCompany = new Map<string, JobRow[]>()
  const applicationsByCompany = new Map<string, number>()
  for (const row of data.rows) {
    const key = companyNameKey(row.company)
    if (key) {
      rolesByCompany.set(key, (rolesByCompany.get(key) ?? 0) + 1)
      const jobs = collectedJobsByCompany.get(key) ?? []
      jobs.push(row)
      collectedJobsByCompany.set(key, jobs)
    }
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
        collectedJobs: [...(collectedJobsByCompany.get(companyKey) ?? [])]
          .sort((left, right) => right.score - left.score),
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
    watching: data.companies.filter((company) => (
      company.lifecycle === 'watching' && company.status === 'active'
    )).length,
    known: data.companies.filter((company) => company.lifecycle === 'known').length,
    paused: data.companies.filter((company) => (
      company.lifecycle === 'watching' && company.status === 'paused'
    )).length,
    needsSetup: data.companies.filter((company) => (
      company.lifecycle === 'watching' && company.resolution_status !== 'resolved'
    )).length,
  }
}

export function monitorCheckAge(checkedAt: string, now = Date.now()): string {
  const age = daysSince(checkedAt, now)
  if (age === null) return 'not yet'
  if (age <= 0) return 'today'
  if (age === 1) return 'yesterday'
  return `${age}d ago`
}