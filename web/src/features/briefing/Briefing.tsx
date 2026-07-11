// The "Briefing" lens — a calm, editorial "state of your search". Purely
// presentational: it renders an already-derived `Briefing` (see `@/lib/briefing`)
// as a written weekly brief — a balanced headline, a slim line of figures, then
// three quiet text-forward sections — and reports role opens upward. No data
// fetching, no mutation.

import { Card } from '@/ui'
import type { Briefing, BriefingItem, BriefingMatch, ItemTone } from '@/lib/briefing'
import type { Tier } from '@/lib/schema'

export interface BriefingProps {
  briefing: Briefing
  onOpen: (jobId: string) => void
  /** Show the slim figures line under the headline. Hidden on Home, where the
   *  dashboard already renders KPI tiles. Defaults to true. */
  showFigures?: boolean
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ')
}

/** ItemTone → accent color for the small round dots on the list rows. */
const TONE_COLOR: Record<ItemTone, string> = {
  brand: 'var(--brand-coral)',
  good: 'var(--good)',
  stretch: 'var(--stretch)',
  danger: 'var(--hot)',
  neutral: 'var(--ink-3)',
}

/** Tier → accent color for the fresh-match micro-labels (matches the legend hues). */
const TIER_COLOR: Record<Tier, string> = {
  Strong: 'var(--strong)',
  Good: 'var(--good)',
  Stretch: 'var(--stretch)',
  Skip: 'var(--skip)',
}

/** A "This week" / "Needs you" row: a toned dot beside a line of copy. Clickable
 *  when the item carries a jobId, otherwise a plain, quiet line. */
function ItemRow({ item, onOpen }: { item: BriefingItem; onOpen: (jobId: string) => void }) {
  const dot = (
    <span
      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
      style={{ background: TONE_COLOR[item.tone] }}
      aria-hidden="true"
    />
  )
  if (item.jobId) {
    const jobId = item.jobId
    return (
      <button
        type="button"
        onClick={() => onOpen(jobId)}
        className="flex w-full items-start gap-2.5 rounded-card py-1.5 text-left text-[14px] text-ink-2 transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
      >
        {dot}
        {item.text}
      </button>
    )
  }
  return (
    <div className="flex items-start gap-2.5 py-1.5 text-[14px] text-ink-2">
      {dot}
      {item.text}
    </div>
  )
}

/** A "Fresh matches" row: company + title on the left, tier + score on the right. */
function MatchRow({ match, onOpen }: { match: BriefingMatch; onOpen: (jobId: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(match.jobId)}
      className="-mx-2 flex w-full items-center gap-3 rounded-card px-2 py-1.5 text-left transition-colors hover:bg-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-medium text-ink">{match.company}</span>
        <span className="block truncate text-[13px] text-ink-3">{match.title}</span>
      </span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="text-[11px] font-semibold uppercase" style={{ color: TIER_COLOR[match.tier] }}>
          {match.tier}
        </span>
        <span className="text-[12px] text-ink-3">{match.score}</span>
      </span>
    </button>
  )
}

/**
 * The Briefing brief: a headline + subhead and three card sections on the state of
 * the search — headline, a slim figure line, and three text-forward sections
 * ("This week", "Needs you", "Fresh matches").
 */
export function Briefing({ briefing, onOpen, showFigures = true }: BriefingProps) {
  return (
    <div className="space-y-5">
      <header className="max-w-3xl">
        <h2 className="font-display text-xl font-semibold leading-snug text-balance text-ink">
          {briefing.headline}
        </h2>
        <p className="mt-1 text-sm text-ink-3">{briefing.subhead}</p>
      </header>

      {showFigures && (
        <div className="flex flex-wrap items-stretch gap-y-2">
          {briefing.figures.map((fig, i) => (
            <div key={fig.key} className={cx('flex flex-col', i > 0 && 'ml-4 border-l border-line pl-4')}>
              <span
                className={cx('text-2xl font-semibold', !fig.accent && 'text-ink')}
                style={fig.accent ? { color: fig.accent } : undefined}
              >
                {fig.value}
              </span>
              <span className="text-[11px] uppercase tracking-wide text-ink-3">{fig.label}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card title="This week">
          {briefing.moved.length === 0 ? (
            <p className="text-sm text-ink-3">Quiet week so far.</p>
          ) : (
            <div className="-my-1.5">
              {briefing.moved.map((item) => (
                <ItemRow key={item.id} item={item} onOpen={onOpen} />
              ))}
            </div>
          )}
        </Card>

        <Card title="Needs you">
          {briefing.needs.length === 0 ? (
            <p className="text-sm text-ink-3">You're all caught up.</p>
          ) : (
            <div className="-my-1.5">
              {briefing.needs.map((item) => (
                <ItemRow key={item.id} item={item} onOpen={onOpen} />
              ))}
            </div>
          )}
        </Card>

        <Card title="Fresh matches" className="md:col-span-2 xl:col-span-1">
          {briefing.matches.length === 0 ? (
            <p className="text-sm text-ink-3">No new matches right now.</p>
          ) : (
            <div className="-my-1">
              {briefing.matches.map((m) => (
                <MatchRow key={m.jobId} match={m} onOpen={onOpen} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
