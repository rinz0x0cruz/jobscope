import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Settings } from '@/features/settings'
import type { SettingsProps } from '@/features/settings'
import { ScoreFormatProvider } from '@/hooks/useScoreFormat'
import type { Profile } from '@/lib/schema'

const profile: Profile = {
  resume: 'security-consulting',
  seniority: 'Senior',
  years_experience: 8,
  search_terms: ['Security Engineer', 'AppSec'],
  locations: ['Remote', 'Berlin'],
  remote: true,
  top_skills: ['Python', 'Threat Modeling'],
}

function renderSettings(over: Partial<SettingsProps> = {}) {
  const onLock = vi.fn()
  render(
    <ScoreFormatProvider>
      <Settings profile={profile} generated="2026-07-02T10:00:00Z" total={42} onLock={onLock} {...over} />
    </ScoreFormatProvider>,
  )
  return { onLock }
}

describe('Settings lens', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
  })

  it('switches the match-score format and persists it', () => {
    renderSettings()
    const grade = screen.getByRole('radio', { name: 'Grade' })
    expect(grade).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(grade)
    expect(grade).toHaveAttribute('aria-checked', 'true')
    expect(localStorage.getItem('jobscope-score-format')).toBe('grade')
  })

  it('applies and persists the theme choice', () => {
    renderSettings()
    fireEvent.click(screen.getByRole('radio', { name: 'Light' }))
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(localStorage.getItem('jobscope-theme')).toBe('light')
  })

  it('shows the résumé profile summary', () => {
    renderSettings()
    expect(screen.getByText('security-consulting')).toBeInTheDocument()
    expect(screen.getByText('Security Engineer')).toBeInTheDocument()
    expect(screen.getByText('Threat Modeling')).toBeInTheDocument()
  })

  it('omits the profile card when there is no profile', () => {
    renderSettings({ profile: null })
    expect(screen.queryByText('Résumé profile')).not.toBeInTheDocument()
  })

  it('locks the session when Lock is pressed', () => {
    const { onLock } = renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /Lock/ }))
    expect(onLock).toHaveBeenCalledTimes(1)
  })

  it('summarises the dataset in the footer', () => {
    renderSettings()
    expect(screen.getByText(/42 roles/)).toBeInTheDocument()
    expect(screen.getByText(/updated/)).toBeInTheDocument()
  })

  it('uses the singular for a single role', () => {
    renderSettings({ total: 1 })
    expect(screen.getByText(/1 role\b/)).toBeInTheDocument()
  })

  it('shows the sync controls', () => {
    renderSettings()
    expect(screen.getByText('Sync')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pull latest' })).toBeInTheDocument()
  })

  it('connects and disconnects a GitHub token', () => {
    vi.stubGlobal('prompt', () => 'ghp_test123')
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: 'Connect GitHub token' }))
    expect(localStorage.getItem('jobscope-gh-token')).toBe('ghp_test123')
    expect(screen.getByText('Token connected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Disconnect' }))
    expect(localStorage.getItem('jobscope-gh-token')).toBeNull()
    vi.unstubAllGlobals()
  })
})
