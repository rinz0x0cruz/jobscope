import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PipelinePreview, PipelineView } from '@/features/pipeline'
import { application } from './factories'

const applications = [
  application({ job_id: 'a', company: 'Acme', status: 'applied' }),
  application({ job_id: 'i', company: 'Interview Co', status: 'interview' }),
  application({ job_id: 'o', company: 'Offer Co', status: 'offer' }),
]

describe('PipelineView', () => {
  it('keeps the graph and filters the application register', () => {
    render(<PipelineView applications={applications} onOpen={() => {}} />)
    expect(screen.getByText('Applied 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Offer · 1' }))
    expect(screen.getByText('Offer Co')).toBeInTheDocument()
    expect(screen.queryByText('Interview Co')).not.toBeInTheDocument()
  })

  it('opens an application row', () => {
    const onOpen = vi.fn()
    render(<PipelineView applications={applications} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Acme — Engineer' }))
    expect(onOpen).toHaveBeenCalledWith('a')
  })

  it('surfaces applications awaiting a response in the feed preview', () => {
    const onOpenPipeline = vi.fn()
    render(<PipelinePreview applications={applications} onOpenPipeline={onOpenPipeline} />)
    expect(screen.getByText('Awaiting response')).toBeInTheDocument()
    expect(screen.getByText('33% of tracked applications')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Open full pipeline/ }))
    expect(onOpenPipeline).toHaveBeenCalledOnce()
  })
})
