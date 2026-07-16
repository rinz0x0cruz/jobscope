import { useMemo, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { ExternalLink, Link2, Search, X } from 'lucide-react'
import { toast } from 'sonner'
import type { Application, ApplicationEvent, JobRow } from '@/lib/schema'
import { TIER_COLOR } from '@/lib/schema'
import { signalColor, statusColor, statusLabel } from '@/components/applications/constants'
import { compLabel } from '@/lib/format'
import { scoreToGrade } from '@/lib/gamification'
import { useScoreFormat } from '@/hooks/useScoreFormat'
import { OfferEditor } from '@/components/OfferEditor'
import { RecruiterOutreach } from '@/components/RecruiterOutreach'
import { presentFitRationale, presentJobDescription, type DescriptionBlock } from '@/lib/jobPresentation'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-border px-5 py-5 sm:px-6">
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
  const blocks = useMemo(() => presentJobDescription(text), [text])
  const lines = useMemo(() => blocks.map((block) => block.text), [blocks])
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
            <div className="space-y-2 font-reader text-[16px] leading-7 text-dim">
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
          <div
            className={`space-y-3 ${
              !expanded && long ? 'max-h-64 overflow-hidden' : ''
            }`}
          >
            <DescriptionBlocks blocks={blocks} />
          </div>
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

function DescriptionBlocks({ blocks }: { blocks: DescriptionBlock[] }) {
  const content: ReactNode[] = []
  for (let index = 0; index < blocks.length;) {
    const block = blocks[index]
    if (block.type === 'bullet') {
      const bullets: DescriptionBlock[] = []
      while (index < blocks.length && blocks[index].type === 'bullet') {
        bullets.push(blocks[index])
        index += 1
      }
      content.push(
        <ul key={`bullets-${index}`} className="list-disc space-y-2 pl-5 font-reader text-[16px] leading-7 text-dim marker:text-accent">
          {bullets.map((bullet, bulletIndex) => <li key={bulletIndex}>{bullet.text}</li>)}
        </ul>,
      )
      continue
    }
    content.push(
      block.type === 'heading' ? (
        <h4 key={index} className="pt-1 text-[12px] font-semibold uppercase text-fg">{block.text}</h4>
      ) : (
        <p key={index} className="font-reader text-[16px] leading-7 text-dim">{block.text}</p>
      ),
    )
    index += 1
  }
  return content
}

function money(n: number, currency?: string): string {
  const sym = !currency || currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : ''
  return `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

const SIGNAL_LABEL: Record<string, string> = {
  confirmation: 'Confirmation',
  recruiter: 'Recruiter',
  assessment: 'Assessment',
  interview: 'Interview',
  offer: 'Offer',
  rejection: 'Rejection',
  other: 'Update',
}

/** Short, timezone-safe date for a timeline entry ("Jul 8"). */
function fmtEventDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '')
  if (!m) return iso || ''
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/**
 * The application's email thread — the "mail summary" surfaced from the board:
 * one entry per scanned email (signal, date, subject, sender, and a one-line
 * body preview present when inbox.store_snippets is enabled).
 */
function EmailTimeline({ events }: { events: ApplicationEvent[] }) {
  return (
    <Section title={`Emails (${events.length})`}>
      <ol className="space-y-3">
        {events.map((ev, i) => {
          const color = signalColor(ev.signal)
          const label = SIGNAL_LABEL[ev.signal] ?? ev.signal ?? 'Update'
          return (
            <li key={i} className="relative border-l border-border pl-4">
              <span
                aria-hidden="true"
                className="absolute -left-[4.5px] top-1 h-2 w-2 rounded-full"
                style={{ background: color, boxShadow: '0 0 0 2px var(--bg2)' }}
              />
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color }}>
                  {label}
                </span>
                <time className="shrink-0 text-[11px] text-mute">{fmtEventDate(ev.date)}</time>
              </div>
              {ev.subject && (
                <div className="mt-0.5 text-[13px] font-medium leading-snug text-fg">{ev.subject}</div>
              )}
              {ev.from && <div className="mt-0.5 text-[11px] text-mute">{ev.from}</div>}
              {ev.summary && <p className="mt-1 text-[12px] leading-relaxed text-dim">{ev.summary}</p>}
            </li>
          )
        })}
      </ol>
    </Section>
  )
}

/**
 * Drawer body for an applied role that no longer has a live match row (it aged
 * out of the fresh feed): a compact header + the email timeline, so opening a
 * board card always surfaces the mail summary.
 */
export function ApplicationReader({ app, onClose }: { app: Application; onClose: () => void }) {
  return (
    <>
      <div className="flex items-start gap-3 px-5 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold leading-snug">
            {app.title || app.company || 'Application'}
          </h2>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-dim">
            <span className="font-medium text-fg">{app.company || '—'}</span>
            <span style={{ color: statusColor(app.status) }}>· {statusLabel(app.status)}</span>
            {app.applied_at && <span className="text-mute">· applied {fmtEventDate(app.applied_at)}</span>}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-border text-dim transition hover:border-border-h hover:text-fg lg:h-8 lg:w-8"
        >
          <X size={15} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {app.timeline.length > 0 ? (
          <EmailTimeline events={app.timeline} />
        ) : (
          <Section title="Emails">
            <p className="text-[13px] text-mute">No emails linked to this application yet.</p>
          </Section>
        )}
        <OfferEditor
          key={`${app.job_id}:${app.interview_at}:${app.salary_offered}:${app.offer_accepted}`}
          app={app}
        />
        <RecruiterOutreach key={`${app.job_id}:followup`} jobId={app.job_id} followup />
      </div>
    </>
  )
}

export function RoleReader({
  job,
  application,
  allRows,
  onOpen,
  onClose,
}: {
  job: JobRow
  application?: Application | null
  allRows: JobRow[]
  onOpen: (id: string) => void
  onClose: () => void
}) {
  const e = job.enrich
  const stock = e.stock
  const comp = compLabel(job)
  const { format } = useScoreFormat()
  const fit = useMemo(() => presentFitRationale(job.rationale), [job.rationale])
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
          {format === 'grade' ? scoreToGrade(job.score) : Math.round(job.score)}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold leading-tight">{job.title}</h2>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-dim">
            <span className="font-medium text-fg">{job.company || '—'}</span>
            {job.place && <span className="text-mute">· {job.place}</span>}
            {job.remote_scope && <span className="text-mute">· {job.remote_scope}</span>}
            <span className="text-mute">· {job.tier}</span>
            {job.stale && (
              <span
                className="rounded-full bg-bg px-1.5 py-0.5 text-[11px] text-mute"
                title={job.posted_age_days != null ? `Posted ${job.posted_age_days}d ago \u2014 likely stale` : 'Likely stale'}
              >
                stale
              </span>
            )}
            {job.remote_mismatch && (
              <span
                className="rounded-full px-1.5 py-0.5 text-[11px]"
                style={{ color: 'var(--hot)', background: 'color-mix(in srgb, var(--hot) 14%, transparent)' }}
                title="Tagged remote, but the description mentions onsite/hybrid"
              >
                remote?
              </span>
            )}
            {job.contacts.length > 0 && (
              <span
                className="rounded-full px-1.5 py-0.5 text-[11px]"
                style={{ color: 'var(--strong)', background: 'color-mix(in srgb, var(--strong) 14%, transparent)' }}
                title="A referral path exists for this company"
              >
                referral
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={copyLink}
            aria-label="Copy link"
            className="grid h-11 w-11 place-items-center rounded-lg border border-border text-dim transition hover:border-border-h hover:text-fg lg:h-8 lg:w-8"
          >
            <Link2 size={15} />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-11 w-11 place-items-center rounded-lg border border-border text-dim transition hover:border-border-h hover:text-fg lg:h-8 lg:w-8"
          >
            <X size={15} />
          </button>
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
        {job.sources.length > 1 && (
          <div className="mt-2 text-[12px] text-mute">
            Also on{' '}
            {job.sources.slice(1).map((s, i) => (
              <span key={s.url}>
                {i > 0 && ', '}
                <a href={s.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  {s.source}
                </a>
              </span>
            ))}
          </div>
        )}
        {job.coverage_pct != null && (
          <div className="mt-3">
            <div className="mb-1 flex items-center justify-between text-[11px] text-mute">
              <span>Résumé covers this JD</span>
              <span className="tnum text-dim">{Math.round(job.coverage_pct)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${Math.max(0, Math.min(100, job.coverage_pct))}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* scrollable sections */}
      <div className="min-h-0 flex-1 overflow-auto">
        {application && application.timeline.length > 0 && (
          <EmailTimeline events={application.timeline} />
        )}
        <RecruiterOutreach key={job.id} jobId={job.id} />
        {job.description && <JobDescription text={job.description} />}

        {job.brief && (
          <Section title="Company brief">
            <p className="whitespace-pre-wrap font-reader text-[16px] leading-7 text-dim">{job.brief}</p>
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
            {fit.metrics.length > 0 ? (
              <div className="space-y-3">
                <dl className="grid grid-cols-3 border-y border-border">
                  {fit.metrics.map((metric, index) => (
                    <div key={metric.label} className={`py-2.5 text-center ${index > 0 ? 'border-l border-border' : ''}`}>
                      <dt className="text-[10px] uppercase text-mute">{metric.label}</dt>
                      <dd className="mt-0.5 font-mono text-base font-semibold text-fg">{metric.value}%</dd>
                    </div>
                  ))}
                </dl>
                {fit.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {fit.skills.map((skill) => (
                      <span key={skill} className="rounded-full border border-border bg-bg px-2.5 py-1 text-[11px] text-dim">
                        {skill}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-mute">
                  {fit.company && <span>{fit.company} company</span>}
                  {fit.route && <span>{fit.route}</span>}
                </div>
                {fit.warning && <p className="text-[12px] text-hot">{fit.warning}</p>}
              </div>
            ) : (
              <p className="font-reader text-[16px] leading-7 text-dim">{fit.fallback}</p>
            )}
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
  application,
  allRows,
  onOpen,
  onClose,
  enabled = true,
}: {
  job: JobRow | null
  application?: Application | null
  allRows: JobRow[]
  onOpen: (id: string) => void
  onClose: () => void
  enabled?: boolean
}) {
  return (
    <Dialog.Root open={enabled && (!!job || !!application)} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="js-overlay fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby={undefined}
          aria-label={job ? `Role details: ${job.title}` : application ? `Application details: ${application.company}` : 'Details'}
          className="js-drawer fixed right-0 top-0 z-50 flex h-full w-full max-w-xl flex-col border-l border-border bg-bg2 shadow-2xl outline-none"
        >
          {job ? (
            <RoleReader
              job={job}
              application={application}
              allRows={allRows}
              onOpen={onOpen}
              onClose={onClose}
            />
          ) : application ? (
            <ApplicationReader app={application} onClose={onClose} />
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
