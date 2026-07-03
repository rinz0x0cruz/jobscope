import type { JobRow } from './schema'
import { FACETS, FACET_KEYS, type FacetKey, type SearchState, type TabValue } from './urlState'

export function isClosed(r: JobRow): boolean {
  return (!!r.status && r.status !== 'open') || !!r.closed_at
}

/** Tier tab + hide-closed, before search and facets. */
export function tabPool(rows: JobRow[], tab: TabValue, hideClosed: boolean): JobRow[] {
  return rows.filter((r) => {
    if (hideClosed && isClosed(r)) return false
    if (tab !== 'all' && tab !== 'overview' && tab !== 'applications' && r.tier !== tab) return false
    return true
  })
}

function getter(key: FacetKey): (r: JobRow) => string {
  return FACETS.find((f) => f.key === key)!.get
}

function passesFacet(r: JobRow, key: FacetKey, selected: string[]): boolean {
  if (selected.length === 0) return true
  return selected.includes(getter(key)(r))
}

/** Apply every facet selection, optionally skipping one (for that facet's own counts). */
export function applyFacets(rows: JobRow[], sel: SearchState, except?: FacetKey): JobRow[] {
  return rows.filter((r) =>
    FACET_KEYS.every((k) => (k === except ? true : passesFacet(r, k, sel[k]))),
  )
}

export interface FacetOption {
  value: string
  count: number
}

/** Options + counts for one facet, honoring the OTHER active facets. */
export function facetOptions(pool: JobRow[], sel: SearchState, key: FacetKey): FacetOption[] {
  const get = getter(key)
  const contextual = applyFacets(pool, sel, key)
  const counts = new Map<string, number>()
  for (const r of contextual) {
    const v = get(r)
    if (!v) continue
    counts.set(v, (counts.get(v) ?? 0) + 1)
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
}

export interface ActiveChip {
  key: FacetKey
  value: string
}

export function activeChips(sel: SearchState): ActiveChip[] {
  const out: ActiveChip[] = []
  for (const k of FACET_KEYS) for (const v of sel[k]) out.push({ key: k, value: v })
  return out
}

export function countActive(sel: SearchState): number {
  return FACET_KEYS.reduce((n, k) => n + sel[k].length, 0)
}

/** Toggle a value in a facet's selection array (immutable). */
export function toggleValue(selected: string[], value: string): string[] {
  return selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]
}

// --- grouping ---

export interface JobItem {
  type: 'job'
  row: JobRow
}
export interface HeaderItem {
  type: 'header'
  company: string
  count: number
}
export type DisplayItem = JobItem | HeaderItem

/** Flatten rows into display items; when grouping, insert a company header before
 *  each group and drop the jobs of collapsed companies. Company order follows the
 *  first (highest-scoring) row seen for that company. */
export function buildDisplayItems(
  rows: JobRow[],
  group: boolean,
  collapsed: ReadonlySet<string>,
): DisplayItem[] {
  if (!group) return rows.map((row) => ({ type: 'job', row }))
  const byCompany = new Map<string, JobRow[]>()
  for (const r of rows) {
    const c = r.company || '—'
    const arr = byCompany.get(c)
    if (arr) arr.push(r)
    else byCompany.set(c, [r])
  }
  const items: DisplayItem[] = []
  for (const [company, jobs] of byCompany) {
    items.push({ type: 'header', company, count: jobs.length })
    if (!collapsed.has(company)) for (const row of jobs) items.push({ type: 'job', row })
  }
  return items
}
