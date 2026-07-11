import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Home } from '@/features/home'
import { buildOverview } from '@/lib/overview'
import { buildBriefing } from '@/lib/briefing'
import { application, dashboard, jobRow } from './factories'

const data = dashboard({
  total: 2,
  rows: [
    jobRow({ id: 'a', company: 'Stripe', tier: 'Strong', score: 90 }),
    jobRow({ id: 'b', company: 'Globex' }),
  ],
  applications: [application({ job_id: 'a', company: 'Stripe', status: 'applied' })],
})

function renderHome() {
  render(
    <Home
      model={buildOverview(data)}
      briefing={buildBriefing(data)}
      apps={data.applications ?? []}
      onOpen={() => {}}
    />,
  )
}

describe('Home lens', () => {
  it('renders KPIs, chart cards, the pipeline flow, and the narrative', () => {
    renderHome()
    expect(screen.getByText('Roles tracked')).toBeInTheDocument() // KPI tile
    expect(screen.getByText('Fit distribution')).toBeInTheDocument() // chart card
    expect(screen.getByText('Pipeline flow')).toBeInTheDocument() // pipeline flow card
    expect(screen.getByText('Sources')).toBeInTheDocument() // restored chart
    expect(screen.getByText('Fresh matches')).toBeInTheDocument() // narrative section
  })

  it('hides the Briefing figures row since the KPI tiles replace it', () => {
    renderHome()
    expect(screen.queryByText('In play')).not.toBeInTheDocument()
  })
})
