import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PipelineFlow } from '@/features/home'
import { application } from './factories'

describe('PipelineFlow', () => {
  it('renders the flow with stage labels derived from applications', () => {
    const apps = [
      application({ job_id: '1', status: 'applied' }), // no response
      application({ job_id: '2', status: 'interview' }), // reached interview, in process
      application({ job_id: '3', status: 'offer' }), // reached interview, offer
      application({ job_id: '4', status: 'rejected' }), // rejected before interview
    ]
    render(<PipelineFlow apps={apps} />)
    expect(screen.getByText('Applied 4')).toBeInTheDocument()
    expect(screen.getByText('Interview 2')).toBeInTheDocument() // interview + offer
    expect(screen.getByText('Offer 1')).toBeInTheDocument()
    expect(screen.getByText('In process 1')).toBeInTheDocument()
  })

  it('shows an empty state when there is no submitted pipeline', () => {
    render(<PipelineFlow apps={[]} />)
    expect(screen.getByText(/No applications in the pipeline yet/i)).toBeInTheDocument()
  })
})
