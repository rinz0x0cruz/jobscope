import { useMemo } from 'react'
import type { Application } from '@/lib/schema'
import { trackSpotlight } from '@/lib/spotlight'
import { FOLLOWUP_DAYS, GHOST_DAYS, followupsDue, ghosted, timing, type StaleApp } from '@/lib/pipeline'

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-2xl font-semibold tnum" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      <span className="text-[11px] text-mute">{label}</span>
    </div>
  )
}

function AppRow({ item, onOpen }: { item: StaleApp; onOpen?: (id: string) => void }) {
  const a = item.app
  const clickable = !!(onOpen && a.job_id)
  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={() => clickable && onOpen!(a.job_id)}
      className="flex w-full items-center gap-3 rounded-[10px] border border-border bg-card px-3 py-2 text-left text-[12.5px] transition enabled:hover:border-border-h enabled:hover:bg-card-h disabled:cursor-default"
    >
      <span className="min-w-0 flex-1 truncate text-fg">{a.company || '—'}</span>
      <span className="hidden min-w-0 flex-1 truncate text-mute sm:block">{a.title || '—'}</span>
      <span className="shrink-0 tnum text-dim">{item.daysSinceApplied}d silent</span>
    </button>
  )
}

/** "Pipeline health": surfaces follow-ups due (#29), likely-ghosted applications
 *  (#27), and response timing (#28) — all derived from the email timeline. */
export function PipelineHealth({ apps, onOpen }: { apps: Application[]; onOpen?: (id: string) => void }) {
  const { due, ghost, t } = useMemo(
    () => ({ due: followupsDue(apps), ghost: ghosted(apps), t: timing(apps) }),
    [apps],
  )

  // Nothing actionable and no timing signal yet -> hide entirely.
  if (due.length === 0 && ghost.length === 0 && t.medianDaysToReply === null) return null

  const fmtD = (n: number | null) => (n === null ? '—' : `${n}d`)

  return (
    <section
      className="js-gradient-card js-spotlight-card flex flex-col gap-4 rounded-[14px] border border-border bg-card p-4"
      onPointerMove={trackSpotlight}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Pipeline health</h3>
        <span className="text-xs text-mute">follow-ups, ghosting &amp; response timing</span>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat
          label={`Follow-ups due (${FOLLOWUP_DAYS}d+)`}
          value={String(due.length)}
          tone={due.length ? 'var(--accent)' : undefined}
        />
        <Stat
          label={`Likely ghosted (${GHOST_DAYS}d+)`}
          value={String(ghost.length)}
          tone={ghost.length ? 'var(--hot)' : undefined}
        />
        <Stat label="Median to reply" value={fmtD(t.medianDaysToReply)} />
        <Stat label="Median to interview" value={fmtD(t.medianDaysToInterview)} />
      </div>

      {(due.length > 0 || ghost.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          {due.length > 0 && (
            <div>
              <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-mute">
                Follow up
              </div>
              <div className="flex flex-col gap-1.5">
                {due.slice(0, 6).map((s) => (
                  <AppRow key={s.app.job_id || s.app.company + s.app.title} item={s} onOpen={onOpen} />
                ))}
              </div>
            </div>
          )}
          {ghost.length > 0 && (
            <div>
              <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-mute">
                Likely ghosted
              </div>
              <div className="flex flex-col gap-1.5">
                {ghost.slice(0, 6).map((s) => (
                  <AppRow key={s.app.job_id || s.app.company + s.app.title} item={s} onOpen={onOpen} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
