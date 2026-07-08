// Client-side "gamification" derivations (issue #35): a letter-grade view of the
// fit score, application velocity/streaks, and a single composite "Chances"
// indicator. Everything is computed from data already in the dashboard payload,
// so there is no change to the Python↔TS contract.
import { pipelineMetrics, pct } from '@/components/applications/constants'
import { daysSince } from '@/lib/pipeline'
import type { Application, JobRow } from '@/lib/schema'

export type Grade = 'A' | 'B' | 'C' | 'D' | 'F'

// Grade colours reuse the tier palette so a grade never visually contradicts the
// tier it maps from (Strong→A/B, Good→C, Stretch→D, Skip→F).
export const GRADE_COLOR: Record<Grade, string> = {
  A: 'var(--strong)',
  B: 'var(--strong)',
  C: 'var(--good)',
  D: 'var(--stretch)',
  F: 'var(--skip)',
}

/** Map a 0–100 fit score to a letter grade. Bands are aligned to the tier cutoffs
 *  (Strong ≥75, Good ≥55, Stretch ≥35) so a grade and its tier never disagree. */
export function scoreToGrade(score: number): Grade {
  const s = Math.round(score)
  if (s >= 85) return 'A'
  if (s >= 75) return 'B'
  if (s >= 55) return 'C'
  if (s >= 35) return 'D'
  return 'F'
}

function clamp(n: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, n))
}

// Statuses that mean a real submission happened (mirrors the funnel model).
const SUBMITTED_STATUSES = new Set(['applied', 'interview', 'offer', 'rejected'])

export interface Velocity {
  applied7: number      // applications submitted in the last 7 days
  applied30: number     // …in the last 30 days
  surfaced7: number     // new roles first seen in the last 7 days
  perWeek: number       // average applications/week over the last 30 days (1 dp)
  streakWeeks: number   // consecutive weeks (ending this week) with ≥1 application
}

/** Application momentum from `applied_at` + `first_seen`. `apps` is empty on the
 *  public build (applications aren't emitted there); velocity then reflects only
 *  freshly-surfaced roles, which is fine. */
export function velocity(rows: JobRow[], apps: Application[], now = Date.now()): Velocity {
  const submittedDays: number[] = []
  for (const a of apps) {
    if (!SUBMITTED_STATUSES.has(a.status || '')) continue
    const d = daysSince(a.applied_at || a.updated, now)
    if (d !== null && d >= 0) submittedDays.push(d)
  }
  const applied7 = submittedDays.filter((d) => d < 7).length
  const applied30 = submittedDays.filter((d) => d < 30).length
  const surfaced7 = rows.filter((r) => {
    const d = daysSince(r.first_seen, now)
    return d !== null && d >= 0 && d < 7
  }).length
  const perWeek = Math.round((applied30 / (30 / 7)) * 10) / 10
  const weeks = new Set(submittedDays.map((d) => Math.floor(d / 7)))
  let streakWeeks = 0
  while (weeks.has(streakWeeks)) streakWeeks += 1
  return { applied7, applied30, surfaced7, perWeek, streakWeeks }
}

// Average fit of your strongest actionable roles (0–100).
function matchStrength(rows: JobRow[], n = 10): number {
  const top = rows
    .filter((r) => r.tier === 'Strong' || r.tier === 'Good')
    .sort((a, b) => b.score - a.score)
    .slice(0, n)
  if (!top.length) return 0
  return Math.round(top.reduce((sum, r) => sum + r.score, 0) / top.length)
}

// Pipeline conversion signal (0–100). Neutral 50 until you have submitted enough
// to read a trend; then it rewards interviews/offers and lightly penalises
// pre-interview rejections, scaled by how much volume backs the signal.
function pipelineStrength(apps: Application[]): number {
  const m = pipelineMetrics(apps)
  if (!m.submitted) return 50
  const signal =
    pct(m.reachedIv, m.submitted) * 0.5 +
    pct(m.offers, m.submitted) * 0.5 -
    pct(m.rejBefore, m.submitted) * 0.25
  const confidence = Math.min(m.submitted / 8, 1)
  return clamp(50 + signal * confidence)
}

// Recent momentum (0–100) from streak length and this week's submissions.
function momentumStrength(v: Velocity): number {
  return clamp((Math.min(v.streakWeeks, 4) / 4) * 55 + (Math.min(v.applied7, 4) / 4) * 45)
}

export interface Chances {
  score: number   // 0–100 composite
  grade: Grade
  label: string
  factors: { matches: number; pipeline: number; momentum: number }
}

/** A single deterministic 0–100 "Chances" indicator blending the strength of your
 *  best matches, your pipeline conversion, and recent momentum. Bounded and
 *  monotonic; neutral (not punitive) before there is any application signal. */
export function chances(apps: Application[], rows: JobRow[], now = Date.now()): Chances {
  const matches = matchStrength(rows)
  const pipeline = pipelineStrength(apps)
  const momentum = momentumStrength(velocity(rows, apps, now))
  const score = Math.round(matches * 0.4 + pipeline * 0.35 + momentum * 0.25)
  return {
    score,
    grade: scoreToGrade(score),
    label: chancesLabel(score),
    factors: { matches, pipeline, momentum },
  }
}

function chancesLabel(score: number): string {
  if (score >= 80) return 'On fire'
  if (score >= 65) return 'Strong momentum'
  if (score >= 50) return 'Building'
  if (score >= 35) return 'Warming up'
  return 'Getting started'
}
