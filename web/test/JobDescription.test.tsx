import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JobDescription } from '@/components/JobDrawer'

const JD = [
  'We are hiring a Senior Security Engineer.',
  'Responsibilities: threat modeling, IAM, and cloud security.',
  'Requirements: 5+ years of security experience.',
].join('\n')

// Feature: archived JD snapshot in the job drawer (issue #30).
describe('JobDescription (JD snapshot)', () => {
  it('renders the archived description under a Job description heading', () => {
    render(<JobDescription text={JD} />)
    expect(screen.getByRole('heading', { name: /job description/i })).toBeInTheDocument()
    expect(screen.getByText(/threat modeling/)).toBeInTheDocument()
  })

  it('filters to matching lines and highlights the query', async () => {
    render(<JobDescription text={JD} />)
    await userEvent.type(screen.getByPlaceholderText(/search this description/i), 'IAM')
    expect(screen.getByText(/1 matching line/)).toBeInTheDocument()
    const marks = document.querySelectorAll('mark')
    expect(marks).toHaveLength(1)
    expect(marks[0].textContent).toBe('IAM')
    // a non-matching line is filtered out
    expect(screen.queryByText(/5\+ years/)).not.toBeInTheDocument()
  })

  it('shows a no-matches message when nothing matches', async () => {
    render(<JobDescription text={JD} />)
    await userEvent.type(screen.getByPlaceholderText(/search this description/i), 'zzzzz')
    expect(screen.getByText(/no matches in this description/i)).toBeInTheDocument()
  })
})
