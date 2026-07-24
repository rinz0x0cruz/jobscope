import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { PipelinePreview } from '@/features/pipeline'
import { application } from './factories'

const applications = [
  application({ job_id: 'a', company: 'Acme', status: 'applied' }),
  application({ job_id: 'i', company: 'Interview Co', status: 'interview' }),
  application({ job_id: 'o', company: 'Offer Co', status: 'offer' }),
]

describe('PipelineView', () => {
  it('surfaces applications awaiting a response in the feed preview', () => {
    const onOpenAnalytics = vi.fn()
    render(<PipelinePreview applications={applications} onOpenAnalytics={onOpenAnalytics} />)
    expect(screen.getByText('Awaiting response')).toBeInTheDocument()
    expect(screen.getByText('33% of tracked applications')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Open analytics/ }))
    expect(onOpenAnalytics).toHaveBeenCalledOnce()
  })
})
