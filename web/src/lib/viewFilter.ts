// A single source of truth for the cockpit's global search: filter the whole
// payload by a free-text query so every lens (built from this view) narrows
// consistently. Matches company / title / location on roles and company / title
// on applications. Empty query returns the data unchanged.

import type { DashboardData } from '@/lib/schema'

export function filterData(data: DashboardData, query: string): DashboardData {
  const q = query.trim().toLowerCase()
  if (!q) return data
  const has = (s: string | null | undefined): boolean => !!s && s.toLowerCase().includes(q)
  const rows = data.rows.filter((r) => has(r.company) || has(r.title) || has(r.location))
  const applications = (data.applications ?? []).filter((a) => has(a.company) || has(a.title))
  return { ...data, rows, applications, total: rows.length }
}
