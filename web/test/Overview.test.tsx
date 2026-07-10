import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Overview } from '@/features/overview'
import type { OverviewModel } from '@/lib/overview'

const model: OverviewModel = {
  kpis: [
    { key: 'roles', label: 'Roles tracked', value: 120 },
    { key: 'strong', label: 'Strong fits', value: 18 },
    { key: 'applied', label: 'Applications', value: 22 },
    { key: 'interviews', label: 'Interviews', value: 4 },
    { key: 'offers', label: 'Offers', value: 1 },
    { key: 'avgfit', label: 'Avg fit', value: 71 },
  ],
  tiers: {
    total: 120,
    segs: [
      { label: 'Strong', value: 18, color: 'var(--strong)', fraction: 0.15, start: 0 },
      { label: 'Good', value: 42, color: 'var(--good)', fraction: 0.35, start: 0.15 },
    ],
  },
  funnel: [
    { key: 'applied', label: 'Applied', value: 22, fraction: 1, color: 'var(--brand-coral)' },
    { key: 'interview', label: 'Interview', value: 4, fraction: 0.18, color: 'var(--stretch)' },
    { key: 'offer', label: 'Offer', value: 1, fraction: 0.05, color: 'var(--strong)' },
  ],
  companies: [
    { label: 'Stripe', value: 5 },
    { label: 'Datadog', value: 3 },
  ],
  locations: [{ label: 'Remote', value: 40 }],
  sources: [{ label: 'greenhouse', value: 30 }],
  trend: [
    { label: '6/1', value: 3 },
    { label: '6/8', value: 7 },
  ],
  scores: [
    { label: '<60', value: 10, color: 'var(--skip)' },
    { label: '90+', value: 6, color: 'var(--strong)' },
  ],
  hasRoles: true,
  hasApplications: true,
}

describe('Overview lens', () => {
  it('renders the KPI tiles', () => {
    render(<Overview model={model} />)
    expect(screen.getByText('Roles tracked')).toBeInTheDocument()
    expect(screen.getByText('Avg fit')).toBeInTheDocument()
    expect(screen.getByText('71')).toBeInTheDocument() // unique KPI value
    expect(screen.getByText('Offers')).toBeInTheDocument()
  })

  it('renders each chart card title', () => {
    render(<Overview model={model} />)
    expect(screen.getByText('Fit distribution')).toBeInTheDocument()
    expect(screen.getByText('Pipeline funnel')).toBeInTheDocument()
    expect(screen.getByText('Roles surfaced · last 8 weeks')).toBeInTheDocument()
    expect(screen.getByText('Score distribution')).toBeInTheDocument()
    expect(screen.getByText('Top companies')).toBeInTheDocument()
  })

  it('shows empty states when there are no roles', () => {
    render(
      <Overview
        model={{
          ...model,
          hasRoles: false,
          tiers: { total: 0, segs: [] },
          companies: [],
          locations: [],
          sources: [],
        }}
      />,
    )
    expect(screen.getByText('No roles yet')).toBeInTheDocument()
    expect(screen.getByText('No companies yet')).toBeInTheDocument()
  })
})
