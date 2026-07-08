import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { Application, JobRow } from '@/lib/schema'
import { Momentum } from '@/components/overview/Momentum'

const row = (p: Partial<JobRow>): JobRow =>
  ({ score: 0, tier: 'Skip', first_seen: '', ...p }) as JobRow

describe('Momentum card', () => {
  it('renders the Chances label plus velocity and factor rows', () => {
    const now = new Date().toISOString()
    const rows = Array.from({ length: 5 }, () => row({ tier: 'Strong', score: 90, first_seen: now }))
    render(<Momentum rows={rows} apps={[] as Application[]} />)

    expect(screen.getByText('Streak')).toBeInTheDocument()
    expect(screen.getByText('New · 7d')).toBeInTheDocument()
    expect(screen.getByText('Matches')).toBeInTheDocument()
    expect(
      screen.getByText(/Getting started|Warming up|Building|Strong momentum|On fire/),
    ).toBeInTheDocument()
  })
})
