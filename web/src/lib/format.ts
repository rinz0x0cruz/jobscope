import type { JobRow } from './schema'

/** Short compensation label for a card pill. */
export function compLabel(row: JobRow): string | null {
  const c = row.enrich.comp
  if (c?.range) return c.range
  if (row.salary) return row.salary
  return null
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
