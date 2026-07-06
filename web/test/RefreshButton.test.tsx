import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/lib/refresh', () => ({ scanNewMail: vi.fn().mockResolvedValue(undefined) }))
import { scanNewMail } from '@/lib/refresh'
import { RefreshButton } from '@/components/RefreshButton'

// Feature: the single header Refresh button that rescans Gmail.
describe('RefreshButton', () => {
  it('renders a labelled refresh control', () => {
    render(<RefreshButton />)
    expect(screen.getByRole('button', { name: /rescan gmail/i })).toBeInTheDocument()
  })

  it('triggers a Gmail rescan on click', async () => {
    render(<RefreshButton />)
    await userEvent.click(screen.getByRole('button', { name: /rescan gmail/i }))
    expect(scanNewMail).toHaveBeenCalledOnce()
  })
})
