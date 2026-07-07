import { useMemo, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ExternalLink, Link2, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import type { JobRow } from '@/lib/schema'
import { TIER_COLOR } from '@/lib/schema'
import { compLabel } from '@/lib/format'
import { RecruiterOutreach } from '@/components/RecruiterOutreach'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-border px-5 py-4">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-mute">{title}</h3>
      {children}
    </section>
  )
}

/** Wrap case-insensitive matches of `q` in a line with a subtle highlight. */
function highlight(line: string, q: string): ReactNode {
  if (!q) return line
  const out: ReactNode[] = []
  const lower = line.toLowerCase()
  const needle = q.toLowerCase()
  let i = 0
  let k = 0
  for (;;) {
    const hit = lower.indexOf(needle, i)
    if (hit < 0) {
      out.push(line.slice(i))
      break
    }
    if (hit > i) out.push(line.slice(i, hit))
    out.push(
      <mark key={k++} className="rounded bg-accent/30 px-0.5 text-fg">
        {line.slice(hit, hit + q.length)}
      </mark>,
    )
    i = hit + q.length
  }
  return out
}

/**
 * Archived job-description snapshot (issue #30): collapsible, with an in-drawer
 * search that filters to matching lines and highlights the hits. Only rendered
 * when a description is present (stripped in the public build).
 */
export function JobDescription({ text }: { text: string }) {
  const [q, setQ] = useState('')
  const [expanded, setExpanded] = useState(false)
  const query = q.trim()
  const lines = useMemo(() => text.split(/\r?\n/), [text])
  const matches = useMemo(
    () => (query ? lines.filter((l) => l.toLowerCase().includes(query.toLowerCase())) : lines),
    [lines, query],
  )
  const long = text.length > 900

  return (
    <Section title="Job description">
      <div className="relative mb-2">
        <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-mute" />
        <input
          value={q}
          onChange={(ev) => setQ(ev.target.value)}
          placeholder="Search this description…"
          className="w-full rounded-lg border border-border bg-bg py-1.5 pl-7 pr-2 text-[12px] text-fg outline-none placeholder:text-mute focus:border-border-h"
        />
      </div>

      {query ? (
        matches.length ? (
          <>
            <div className="mb-1 text-[11px] text-mute">
              {matches.length} matching line{matches.length === 1 ? '' : 's'}
            </div>
            <div className="space-y-1 text-[13px] leading-relaxed text-dim">
              {matches.map((l, i) => (
                <p key={i} className="whitespace-pre-wrap">
                  {highlight(l, query)}
                </p>
              ))}
            </div>
          </>
        ) : (
          <p className="text-[13px] text-mute">No matches in this description.</p>
        )
      ) : (
        <>
          <p
            className={`whitespace-pre-wrap text-[13px] leading-relaxed text-dim ${
              !expanded && long ? 'max-h-64 overflow-hidden' : ''
            }`}
          >
            {text}
          </p>
          {long && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-1.5 text-[12px] font-medium text-accent hover:underline"
            >
              {expanded ? 'Show less' : 'Show full description'}
            </button>
          )}
        </>
      )}
    </Section>
  )
}

function money(n: number, currency?: string): string {
  const sym = !currency || currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : ''
  return `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function DrawerBody({
  job,
  allRows,
  onOpen,
}: {
  job: JobRow
  allRows: JobRow[]
  onOpen: (id: string) => void
}) {
  const e = job.enrich
  const stock = e.stock
  const comp = compLabel(job)
  const others = allRows.filter((r) => r.company === job.company && r.id !== job.id).slice(0, 8)

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(location.href)
      toast.success('Link copied — deep-links to this role')
    } catch {
      toast.error('Copy failed')
    }
  }

  return (
    <>
      {/* header */}
      <div className="flex items-start gap-3 px-5 py-4">
        <span className="mt-0.5 text-2xl font-semibold tnum" style={{ color: TIER_COLOR[job.tier] }}>
          {Math.round(job.score)}
        </span>
        <div className="min-w-0 flex-1">
          <Dialog.Title className="text-[15px] font-semibold leading-snug">{job.title}</Dialog.Title>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-dim">
            <span className="font-medium text-fg">{job.company || '—'}</span>
            {job.place && <span className="text-mute">· {job.place}</span>}
            {job.remote_scope && <span className="text-mute">· {job.remote_scope}</span>}
            <span className="text-mute">· {job.tier}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={copyLink}
            aria-label="Copy link"
            className="grid h-8 w-8 place-items-center rounded-lg border border-border text-dim transition hover:border-border-h hover:text-fg"
          >
            <Link2 size={15} />
          </button>
          <Dialog.Close
            aria-label="Close"
            className="grid h-8 w-8 place-items-center rounded-lg border border-border text-dim transition hover:border-border-h hover:text-fg"
          >
            <X size={15} />
          </Dialog.Close>
        </div>
      </div>

      <div className="px-5 pb-4">
        <a
          href={job.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-3.5 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
        >
          Apply on {job.source || 'source'} <ExternalLink size={14} />
        </a>
      </div>

      {/* scrollable sections */}
      <div className="min-h-0 flex-1 overflow-auto">
        <RecruiterOutreach jobId={job.id} />
        {job.description && <JobDescription text={job.description} />}

        {job.brief && (
          <Section title="Company brief">
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-dim">{job.brief}</p>
          </Section>
        )}

        {(comp || e.comp) && (
          <Section title="Compensation">
            {comp && <div className="text-sm font-medium text-fg">{comp}</div>}
            <div className="mt-1 flex flex-wrap gap-3 text-[13px]">
              {e.comp?.levels_fyi && (
                <a href={e.comp.levels_fyi} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  Levels.fyi salaries ↗
                </a>
              )}
              {e.comp?.levels_search && (
                <a href={e.comp.levels_search} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  Levels.fyi search ↗
                </a>
              )}
            </div>
          </Section>
        )}

        {stock && (
          <Section title="Stock">
            {stock.public === false ? (
              <p className="text-[13px] text-dim">Private / pre-IPO — not publicly traded.</p>
            ) : stock.ticker ? (
              <div className="space-y-2.5">
                <div className="flex items-baseline gap-2">
                  <span className="font-semibold text-fg">{stock.ticker}</span>
                  {typeof stock.price === 'number' && (
                    <span className="text-sm text-dim">{money(stock.price, stock.currency)}</span>
                  )}
                  {typeof stock.change_pct === 'number' && (
                    <span
                      className="text-sm"
                      style={{ color: stock.change_pct >= 0 ? 'var(--strong)' : 'var(--stretch)' }}
                    >
                      {stock.change_pct >= 0 ? '+' : ''}
                      {stock.change_pct.toFixed(2)}%
                    </span>
                  )}
                  {stock.market_cap && <span className="ml-auto text-sm text-mute">{stock.market_cap}</span>}
                </div>
                {typeof stock.week52_low === 'number' && typeof stock.week52_high === 'number' && (
                  <div>
                    <div className="relative h-1.5 rounded-full bg-border">
                      <div
                        className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-bg2 bg-accent"
                        style={{ left: `calc(${Math.max(0, Math.min(100, stock.week52_pos_pct ?? 0))}% - 6px)` }}
                      />
                    </div>
                    <div className="mt-1 flex justify-between text-[11px] text-mute tnum">
                      <span>{money(stock.week52_low, stock.currency)} low</span>
                      <span>{money(stock.week52_high, stock.currency)} high</span>
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </Section>
        )}

        {e.reddit && (e.reddit.summary || e.reddit.sentiment) && (
          <Section title="Reputation (Reddit)">
            {e.reddit.sentiment && (
              <div className="mb-1 text-[13px] text-fg">
                Sentiment: <span className="capitalize text-dim">{e.reddit.sentiment}</span>
                {typeof e.reddit.count === 'number' ? <span className="text-mute"> · {e.reddit.count} threads</span> : null}
              </div>
            )}
            {e.reddit.summary && <p className="text-[13px] leading-relaxed text-dim">{e.reddit.summary}</p>}
          </Section>
        )}

        {e.glassdoor && Object.keys(e.glassdoor).length > 0 && (
          <Section title="Glassdoor">
            <div className="text-[13px] text-dim">
              {'rating' in e.glassdoor ? `Rating: ${String(e.glassdoor.rating)}` : JSON.stringify(e.glassdoor)}
            </div>
          </Section>
        )}

        {e.news && e.news.length > 0 && (
          <Section title="Recent news">
            <ul className="space-y-2">
              {e.news.slice(0, 3).map((n, i) => (
                <li key={i}>
                  <a
                    href={n.link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[13px] text-fg hover:text-accent hover:underline"
                  >
                    {n.title}
                  </a>
                  <div className="text-[11px] text-mute">{[n.source, n.published].filter(Boolean).join(' · ')}</div>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {job.contacts.length > 0 && (
          <Section title="Referral leads">
            <ul className="space-y-1.5">
              {job.contacts.map((c, i) => (
                <li key={i}>
                  <a
                    href={c.url ?? '#'}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[13px] text-accent hover:underline"
                  >
                    🤝 {c.name ?? 'lead'}
                    {c.title ? <span className="text-mute"> — {c.title}</span> : null}
                  </a>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {job.rationale && (
          <Section title="Why this ranks">
            <p className="text-[13px] leading-relaxed text-dim">{job.rationale}</p>
          </Section>
        )}

        {others.length > 0 && (
          <Section title={`More at ${job.company} (${others.length})`}>
            <ul className="space-y-1">
              {others.map((o) => (
                <li key={o.id}>
                  <button
                    type="button"
                    onClick={() => onOpen(o.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] transition hover:bg-card-h"
                  >
                    <span className="tnum font-semibold" style={{ color: TIER_COLOR[o.tier] }}>
                      {Math.round(o.score)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-fg">{o.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>
    </>
  )
}

export function JobDrawer({
  job,
  allRows,
  onOpen,
  onClose,
}: {
  job: JobRow | null
  allRows: JobRow[]
  onOpen: (id: string) => void
  onClose: () => void
}) {
  return (
    <Dialog.Root open={!!job} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="js-overlay fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby={undefined}
          className="js-drawer fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-border bg-bg2 shadow-2xl outline-none"
        >
          {job && <DrawerBody job={job} allRows={allRows} onOpen={onOpen} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
