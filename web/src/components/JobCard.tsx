import type { ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ExternalLink } from 'lucide-react'
import type { JobRow } from '@/lib/schema'
import { TIER_COLOR } from '@/lib/schema'
import { compLabel, daysAgo, stockChange, stockLabel } from '@/lib/format'

function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md border border-border bg-bg2 px-1.5 py-0.5 text-[11px] text-dim">
      {children}
    </span>
  )
}

export function JobCard({ row, onOpen }: { row: JobRow; onOpen: (id: string) => void }) {
  const reduce = useReducedMotion()
  const tierColor = TIER_COLOR[row.tier]
  const comp = compLabel(row)
  const stock = stockLabel(row)
  const chg = stockChange(row)
  const age = daysAgo(row.first_seen)
  const isNew = age !== null && age < 1

  return (
    <motion.article
      whileHover={reduce ? undefined : { y: -2 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      onClick={() => onOpen(row.id)}
      onKeyDown={(ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault()
          onOpen(row.id)
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`Open ${row.title} at ${row.company}`}
      className="cursor-pointer rounded-[14px] border border-border bg-card p-4 outline-none transition-colors hover:border-border-h hover:bg-card-h focus-visible:border-accent"
    >
      <div className="flex items-start gap-3">
        <div className="flex w-11 shrink-0 flex-col items-center pt-0.5">
          <span className="text-lg font-semibold tnum" style={{ color: tierColor }}>
            {Math.round(row.score)}
          </span>
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full"
              style={{ width: `${Math.max(0, Math.min(100, row.score))}%`, background: tierColor }}
            />
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="truncate text-[15px] font-medium leading-snug">{row.title}</h3>
            {isNew && (
              <span className="shrink-0 rounded-full bg-accent-dim px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                new
              </span>
            )}
          </div>

          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-dim">
            <span className="font-medium text-fg">{row.company || '—'}</span>
            {row.place && <span className="text-mute">&middot; {row.place}</span>}
            {row.remote_scope && <span className="text-mute">&middot; {row.remote_scope}</span>}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Pill>{row.tier}</Pill>
            {comp && <Pill>{comp}</Pill>}
            {stock && (
              <Pill>
                {stock}
                {typeof chg === 'number' && (
                  <span style={{ color: chg >= 0 ? 'var(--strong)' : 'var(--stretch)' }}>
                    {' '}
                    {chg >= 0 ? '+' : ''}
                    {chg.toFixed(1)}%
                  </span>
                )}
              </Pill>
            )}
            {row.funding && <Pill>{row.funding}</Pill>}
            {row.source && <Pill>{row.source}</Pill>}
          </div>
        </div>

        <a
          href={row.url}
          target="_blank"
          rel="noreferrer"
          onClick={(ev) => ev.stopPropagation()}
          className="inline-flex shrink-0 items-center gap-1 self-center rounded-[10px] border border-border bg-bg2 px-3 py-1.5 text-[13px] font-medium text-fg transition hover:border-accent hover:text-accent"
        >
          Apply <ExternalLink size={13} />
        </a>
      </div>
    </motion.article>
  )
}
