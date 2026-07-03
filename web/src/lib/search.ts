import Fuse from 'fuse.js'
import type { JobRow } from './schema'

export type JobFuse = Fuse<JobRow>

export function makeFuse(rows: JobRow[]): JobFuse {
  return new Fuse(rows, {
    keys: [
      { name: 'title', weight: 0.5 },
      { name: 'company', weight: 0.3 },
      { name: 'place', weight: 0.1 },
      { name: 'country', weight: 0.1 },
    ],
    threshold: 0.38,
    ignoreLocation: true,
    minMatchCharLength: 2,
  })
}

/** Fuzzy-filter within a pool; empty query returns the pool unchanged (ranked order). */
export function fuzzy(fuse: JobFuse, pool: JobRow[], q: string): JobRow[] {
  const query = q.trim()
  if (!query) return pool
  return fuse.search(query).map((r) => r.item)
}
