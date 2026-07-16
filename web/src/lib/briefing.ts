// Briefing model for the v2 cockpit — an editorial "state of your search".
// Pure derivation over the emitted payload (no contract change): it turns the raw
// pipeline into a headline, a few figures that matter, "what moved this week",
// "what needs you", and a short list of fresh matches worth a look.

import type { DashboardData, Tier } from '@/lib/schema'
import { chances, velocity } from '@/lib/gamification'
import { daysSince, followupsDue, ghosted } from '@/lib/pipeline'

const WEEK = 7

export type ItemTone = 'brand' | 'good' | 'stretch' | 'danger' | 'neutral'

export interface BriefingFigure {
  key: string
  label: string
  value: number
  /** CSS color for the value (theme var), when the figure carries an accent. */
  accent?: string
}

export interface BriefingItem {
  id: string
  text: string
  company?: string
  jobId?: string
  tone: ItemTone
}

export interface BriefingMatch {
  jobId: string
  company: string
  title: string
  tier: Tier
  score: number
}

export interface Briefing {
  headline: string
  subhead: string
  figures: BriefingFigure[]
  moved: BriefingItem[]
  needs: BriefingItem[]
  matches: BriefingMatch[]
}

const MOVED_SIGNAL_TEXT: Record<string, (company: string) => string> = {
  interview: (c) => `Interview step with ${c}`,
  assessment: (c) => `Assessment from ${c}`,
  offer: (c) => `Offer from ${c}`,
  rejection: (c) => `Passed by ${c}`,
  recruiter: (c) => `${c} recruiter reached out`,
}

const MOVED_SIGNAL_TONE: Record<string, ItemTone> = {
  interview: 'good',
  assessment: 'good',
  offer: 'brand',
  rejection: 'danger',
  recruiter: 'neutral',
}

function plural(n: number, one: string, many = `${one}s`): string {
  return n === 1 ? one : many
}

export function buildBriefing(data: DashboardData, now = Date.now()): Briefing {
  const apps = data.applications ?? []
  const rows = data.rows ?? []

  const inPlay = apps.filter((a) => ['applied', 'interview', 'offer'].includes(a.status)).length
  const interviews = apps.filter((a) => a.status === 'interview').length
  const offers = apps.filter((a) => a.status === 'offer').length
  const due = followupsDue(apps, now)
  const quiet = ghosted(apps, now)
  const needsCount = due.length + quiet.length

  const appIds = new Set(apps.map((a) => a.job_id))
  const freshMatches = rows
    .filter((r) => !appIds.has(r.id))
    .filter((r) => (r.tier === 'Strong' || r.tier === 'Good') && r.status === 'open' && !r.closed_at)
    .sort((a, b) => b.score - a.score)
  const v = velocity(rows, apps, now)
  const newStrong = freshMatches.filter((r) => {
    const d = daysSince(r.first_seen, now)
    return d !== null && d >= 0 && d < WEEK
  }).length

  // Headline: lead with the strongest true signal, then flag what needs a nudge.
  const c = chances(apps, rows, now)
  let lead: string
  if (offers > 0) lead = `You have ${offers} ${plural(offers, 'offer')} on the table`
  else if (interviews > 0)
    lead = `${interviews} ${plural(interviews, 'role')} in interviews — keep the momentum`
  else if (inPlay > 0) lead = `${inPlay} ${plural(inPlay, 'application')} in flight`
  else if (freshMatches.length > 0) lead = `${freshMatches.length} matches ready to pursue`
  else lead = 'Let’s get the first applications out'
  const headline = needsCount > 0 ? `${lead}. ${needsCount} ${plural(needsCount, 'thing')} need${needsCount === 1 ? 's' : ''} you.` : `${lead}.`

  const subheadBits = [`${data.total} roles tracked`, `“${c.label}”`]
  if (newStrong > 0) subheadBits.splice(1, 0, `${newStrong} new this week`)
  const subhead = subheadBits.join(' · ')

  const figures: BriefingFigure[] = [
    { key: 'inplay', label: 'In play', value: inPlay },
    { key: 'interviews', label: plural(interviews, 'Interview'), value: interviews, accent: interviews ? 'var(--good)' : undefined },
    { key: 'offers', label: plural(offers, 'Offer'), value: offers, accent: offers ? 'var(--strong)' : undefined },
    { key: 'needs', label: 'Needs you', value: needsCount, accent: needsCount ? 'var(--stretch)' : undefined },
    { key: 'new', label: 'New this week', value: v.surfaced7 },
  ]

  // What moved: submissions + real timeline events inside the last week.
  const moved: BriefingItem[] = []
  for (const a of apps) {
    const dApplied = daysSince(a.applied_at, now)
    if (dApplied !== null && dApplied >= 0 && dApplied < WEEK) {
      moved.push({ id: `${a.job_id}:applied`, text: `Applied to ${a.company}`, company: a.company, jobId: a.job_id, tone: 'neutral' })
    }
    for (const [eventIndex, e] of (a.timeline ?? []).entries()) {
      const mk = MOVED_SIGNAL_TEXT[e.signal]
      if (!mk) continue
      const d = daysSince(e.date, now)
      if (d === null || d < 0 || d >= WEEK) continue
      moved.push({ id: `${a.job_id}:${e.signal}:${e.date}:${eventIndex}`, text: mk(a.company), company: a.company, jobId: a.job_id, tone: MOVED_SIGNAL_TONE[e.signal] ?? 'neutral' })
    }
  }
  moved.sort((x, y) => (y.id > x.id ? 1 : -1))

  // What needs you: follow-ups, then gone-quiet, then ready HR outreach.
  const needs: BriefingItem[] = []
  for (const s of due) {
    needs.push({ id: `due:${s.app.job_id}`, text: `Nudge ${s.app.company} — ${s.daysSinceApplied}d since applying, no reply`, company: s.app.company, jobId: s.app.job_id, tone: 'stretch' })
  }
  for (const s of quiet) {
    needs.push({ id: `ghost:${s.app.job_id}`, text: `${s.app.company} has gone quiet (${s.daysSinceApplied}d)`, company: s.app.company, jobId: s.app.job_id, tone: 'danger' })
  }
  for (const co of data.applied_outreach ?? []) {
    if ((co.contacts ?? []).length === 0) continue
    needs.push({ id: `hr:${co.company}`, text: `Reach out — HR contact ready at ${co.company}`, company: co.company, tone: 'brand' })
  }

  const matches: BriefingMatch[] = freshMatches.slice(0, 5).map((r) => ({
    jobId: r.id,
    company: r.company,
    title: r.title,
    tier: r.tier,
    score: r.score,
  }))

  return { headline, subhead, figures, moved: moved.slice(0, 6), needs: needs.slice(0, 6), matches }
}
