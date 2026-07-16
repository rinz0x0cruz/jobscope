import type { JobRow } from './schema'

/** Short compensation label for a card pill. */
export function compLabel(row: JobRow): string | null {
  const c = row.enrich.comp
  if (c?.range) return c.range
  if (row.salary) return row.salary
  return null
}

function annualize(value: number, interval: string | undefined): number | null {
  const unit = (interval || 'year').toLowerCase()
  if (['year', 'yearly', 'annual', 'annually'].includes(unit)) return value
  if (['month', 'monthly'].includes(unit)) return value * 12
  if (['week', 'weekly'].includes(unit)) return value * 52
  if (['hour', 'hourly'].includes(unit)) return value * 2080
  return null
}

/** Posting midpoint as a percentage of the public market midpoint. */
export function compRatio(row: JobRow): number | null {
  const market = row.enrich.comp
  const postingValues = [row.salary_min, row.salary_max].filter((value): value is number =>
    typeof value === 'number' && value > 0)
  const marketValues = [market?.min, market?.max].filter((value): value is number =>
    typeof value === 'number' && value > 0)
  if (!postingValues.length || !marketValues.length) return null
  const postingCurrency = row.currency.trim().toUpperCase()
  const marketCurrency = (market?.currency || '').trim().toUpperCase()
  if (postingCurrency && marketCurrency && postingCurrency !== marketCurrency) return null
  const postingMidpoint = postingValues.reduce((sum, value) => sum + value, 0) / postingValues.length
  const marketMidpoint = marketValues.reduce((sum, value) => sum + value, 0) / marketValues.length
  const annualPosting = annualize(postingMidpoint, row.salary_interval)
  const annualMarket = annualize(marketMidpoint, market?.interval)
  if (!annualPosting || !annualMarket) return null
  return Math.round((annualPosting / annualMarket) * 100)
}

export function glassdoorRating(row: JobRow): number | null {
  const rating = row.enrich.glassdoor?.rating
  return typeof rating === 'number' && rating >= 0 && rating <= 5 ? rating : null
}

/** Stock label: ticker · market cap, or "Not public" for known-private. */
export function stockLabel(row: JobRow): string | null {
  const s = row.enrich.stock
  if (!s) return null
  if (s.public === false) return 'Not public'
  if (!s.ticker) return null
  return s.market_cap ? `${s.ticker} · ${s.market_cap}` : s.ticker
}

export function stockChange(row: JobRow): number | null {
  const c = row.enrich.stock?.change_pct
  return typeof c === 'number' ? c : null
}

/** Whole days since an ISO timestamp, or null if unparseable. */
export function daysAgo(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  return Math.floor((Date.now() - t) / 86_400_000)
}

export function fmtGenerated(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
