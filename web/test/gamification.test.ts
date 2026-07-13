import { describe, expect, it } from 'vitest'
import type { Application, JobRow } from '@/lib/schema'
import { GRADE_COLOR, chances, scoreToGrade, velocity } from '@/lib/gamification'

const NOW = Date.parse('2026-07-08T00:00:00Z')
const daysAgo = (n: number) => new Date(NOW - n * 86_400_000).toISOString()

// Only the fields the gamification helpers read are set; the rest are cast away.
const row = (p: Partial<JobRow>): JobRow =>
  ({ score: 0, tier: 'Skip', first_seen: '', ...p }) as JobRow
const app = (p: Partial<Application>): Application =>
  ({ status: 'applied', applied_at: '', updated: '', interview_at: '', salary_offered: '', offer_accepted: '', timeline: [], ...p }) as Application

describe('gamification: scoreToGrade', () => {
  it('maps score bands to A–F aligned with the tier cutoffs', () => {
    expect(scoreToGrade(92)).toBe('A')
    expect(scoreToGrade(85)).toBe('A')
    expect(scoreToGrade(80)).toBe('B')
    expect(scoreToGrade(75)).toBe('B')
    expect(scoreToGrade(60)).toBe('C')
    expect(scoreToGrade(40)).toBe('D')
    expect(scoreToGrade(20)).toBe('F')
  })

  it('rounds before banding and colours align with the tier palette', () => {
    expect(scoreToGrade(74.6)).toBe('B') // rounds to 75
    expect(scoreToGrade(54.4)).toBe('D') // rounds to 54 -> Stretch band
    expect(GRADE_COLOR.A).toBe('var(--strong)')
    expect(GRADE_COLOR.C).toBe('var(--good)')
    expect(GRADE_COLOR.F).toBe('var(--skip)')
  })
})

describe('gamification: velocity', () => {
  it('counts submissions in the last 7 / 30 days and roles surfaced this week', () => {
    const apps = [
      app({ status: 'applied', applied_at: daysAgo(1) }),
      app({ status: 'interview', applied_at: daysAgo(5) }),
      app({ status: 'rejected', applied_at: daysAgo(20) }),
      app({ status: 'new', applied_at: daysAgo(2) }), // not submitted -> ignored
    ]
    const rows = [
      row({ first_seen: daysAgo(1) }),
      row({ first_seen: daysAgo(3) }),
      row({ first_seen: daysAgo(10) }), // older than a week
    ]
    const v = velocity(rows, apps, NOW)
    expect(v.applied7).toBe(2)
    expect(v.applied30).toBe(3)
    expect(v.surfaced7).toBe(2)
    expect(v.perWeek).toBe(0.7) // 3 / (30/7)
  })

  it('streaks consecutive weeks ending this week and breaks on a gap', () => {
    const apps = [
      app({ applied_at: daysAgo(1) }), // week 0
      app({ applied_at: daysAgo(8) }), // week 1
      app({ applied_at: daysAgo(22) }), // week 3 (gap at week 2)
    ]
    expect(velocity([], apps, NOW).streakWeeks).toBe(2)
  })

  it('is zero-safe with no data', () => {
    expect(velocity([], [], NOW)).toEqual({
      applied7: 0, applied30: 0, surfaced7: 0, perWeek: 0, streakWeeks: 0,
    })
  })
})

describe('gamification: chances', () => {
  it('is a neutral-low, non-punitive score with no signal', () => {
    const c = chances([], [], NOW)
    expect(c.score).toBe(18) // 0*.4 + 50*.35 + 0*.25
    expect(c.grade).toBe('F')
    expect(c.label).toBe('Getting started')
    expect(c.factors).toEqual({ matches: 0, pipeline: 50, momentum: 0 })
  })

  it('rewards strong matches, interviews/offers, and an active streak', () => {
    const rows = Array.from({ length: 10 }, () => row({ tier: 'Strong', score: 90 }))
    const apps = [
      app({ status: 'offer', applied_at: daysAgo(1),
        timeline: [{ date: daysAgo(3), signal: 'interview', subject: '', from: '', summary: '' }] }),
      app({ status: 'interview', applied_at: daysAgo(2) }),
      app({ status: 'interview', applied_at: daysAgo(9) }),
      ...Array.from({ length: 6 }, (_, i) => app({ status: 'applied', applied_at: daysAgo(3 + i) })),
    ]
    const c = chances(apps, rows, NOW)
    expect(c.score).toBeGreaterThan(70)
    expect(['A', 'B']).toContain(c.grade)
    expect(c.factors.matches).toBe(90)
    expect(c.factors.pipeline).toBeGreaterThan(50)
    expect(c.factors.momentum).toBeGreaterThan(50)
  })

  it('stays bounded 0–100 at the extremes', () => {
    const rows = Array.from({ length: 12 }, () => row({ tier: 'Strong', score: 100 }))
    const apps = Array.from({ length: 20 }, (_, i) => app({ status: 'offer', applied_at: daysAgo(i % 7) }))
    const c = chances(apps, rows, NOW)
    expect(c.score).toBeLessThanOrEqual(100)
    expect(c.score).toBeGreaterThanOrEqual(0)
  })
})
