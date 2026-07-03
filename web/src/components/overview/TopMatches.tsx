import { useMemo, useState } from 'react'
import type { JobRow } from '@/lib/schema'
import { TIER_COLOR } from '@/lib/schema'

type Key = 'score' | 'title' | 'company' | 'tier'

/** Sortable, sticky-header table of the top matches. (Rows open Apply for now;
 *  Phase 5 swaps this for the detail drawer via ?job=.) */
export function TopMatches({ rows }: { rows: JobRow[] }) {
  const [key, setKey] = useState<Key>('score')
  const [dir, setDir] = useState<'asc' | 'desc'>('desc')

  const sorted = useMemo(() => {
    const s = [...rows]
    s.sort((a, b) => {
      const r = key === 'score' ? a.score - b.score : String(a[key]).localeCompare(String(b[key]))
      return dir === 'asc' ? r : -r
    })
    return s
  }, [rows, key, dir])

  const onSort = (k: Key) => {
    if (k === key) setDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setKey(k)
      setDir(k === 'score' ? 'desc' : 'asc')
    }
  }

  const Th = ({ k, label, className = '' }: { k: Key; label: string; className?: string }) => (
    <th
      onClick={() => onSort(k)}
      className={'cursor-pointer select-none px-3 py-2 text-left font-medium text-dim transition hover:text-fg ' + className}
    >
      {label}
      {key === k ? (dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </th>
  )

  return (
    <div className="max-h-[420px] overflow-auto rounded-[12px] border border-border">
      <table className="w-full border-collapse text-[13px]">
        <thead className="sticky top-0 z-10 bg-card">
          <tr className="border-b border-border">
            <Th k="score" label="Score" className="w-16" />
            <Th k="title" label="Role" />
            <Th k="company" label="Company" className="w-44" />
            <Th k="tier" label="Tier" className="w-20" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id} className="border-b border-border/60 transition hover:bg-card-h">
              <td className="px-3 py-2 font-semibold tnum" style={{ color: TIER_COLOR[r.tier] }}>
                {Math.round(r.score)}
              </td>
              <td className="px-3 py-2">
                <a href={r.url} target="_blank" rel="noreferrer" className="transition hover:text-accent">
                  {r.title}
                </a>
              </td>
              <td className="truncate px-3 py-2 text-dim">{r.company}</td>
              <td className="px-3 py-2">
                <span style={{ color: TIER_COLOR[r.tier] }}>{r.tier}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
