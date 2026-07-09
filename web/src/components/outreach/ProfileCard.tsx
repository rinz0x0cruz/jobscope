import type { Profile } from '@/lib/schema'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-border bg-bg2/70 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-mute">{label}</div>
      <div className="mt-0.5 text-[13px] font-medium text-fg">{value}</div>
    </div>
  )
}

function Chips({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div className="mt-3">
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-mute">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((it) => (
          <span key={it} className="rounded-md border border-border bg-bg2 px-2 py-0.5 text-[12px] text-dim">
            {it}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Surfaces the résumé-derived search profile (render._profile_data) — the thing
 *  that drives matching + outreach. Behind the site unlock; null when locked or
 *  before a résumé is imported. */
export function ProfileCard({ profile }: { profile: Profile | null }) {
  if (!profile) {
    return (
      <section className="rounded-[14px] border border-dashed border-border bg-card/60 p-5 text-[13px] text-mute">
        Your résumé profile appears here once the site is unlocked — and after you
        <code className="mx-1 rounded bg-bg2 px-1 py-0.5 text-dim">jobscope resume import</code>
        a résumé and refresh.
      </section>
    )
  }
  return (
    <section className="rounded-[14px] border border-border bg-card p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Your résumé profile</h3>
        <span className="text-[12px] text-mute">résumé: {profile.resume}</span>
      </div>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Stat label="Seniority" value={profile.seniority || '—'} />
        <Stat label="Experience" value={`${profile.years_experience} yr`} />
        <Stat label="Remote" value={profile.remote ? 'Yes' : 'No'} />
        <Stat label="Locations" value={profile.locations.join(', ') || '—'} />
      </div>
      <Chips title="Target roles" items={profile.search_terms} />
      <Chips title="Top skills" items={profile.top_skills} />
    </section>
  )
}
