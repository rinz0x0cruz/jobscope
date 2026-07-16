import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Settings } from '@/features/settings'
import type { SettingsProps } from '@/features/settings'
import { ScoreFormatProvider } from '@/hooks/ScoreFormatProvider'
import type { Profile } from '@/lib/schema'

const profile: Profile = {
  resume: 'security-consulting',
  seniority: 'Senior',
  years_experience: 8,
  search_terms: ['Security Engineer', 'AppSec'],
  locations: ['Remote', 'Berlin'],
  remote: true,
  top_skills: ['Python', 'Threat Modeling'],
  name: 'security-consulting',
  available: ['security-consulting'],
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
    expect(screen.getByRole('heading', { name: 'Data sync' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Scan Gmail' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pull latest' })).toBeInTheDocument()
  })

  it('uploads a resume and promotes the returned profile', async () => {
    const onProfileChange = vi.fn()
    const nextProfile = {
      ...profile,
      name: 'product-security',
      resume: 'product-security',
      available: ['security-consulting', 'product-security'],
    }
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/api/token')) {
        return { ok: true, json: async () => ({ token: 'local-token' }) } as Response
      }
      if (url.endsWith('/api/resume/upload')) {
        return { ok: true, json: async () => ({ ok: true, profile: nextProfile, profile_count: 2, profile_limit: 3 }) } as Response
      }
      return { ok: false, json: async () => ({}) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderSettings({ onProfileChange })

    const name = await screen.findByLabelText('Profile name')
    fireEvent.change(name, { target: { value: 'product-security' } })
    const file = new File(['# Jane\n## Skills\nPython, AWS'], 'product-security.md', { type: 'text/markdown' })
    fireEvent.change(screen.getByLabelText('Resume file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Build profile' }))

    await waitFor(() => expect(onProfileChange).toHaveBeenCalledWith(nextProfile))
    const uploadCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/resume/upload'))
    const body = JSON.parse(String((uploadCall?.[1] as RequestInit).body))
    expect(body.name).toBe('product-security')
    expect(body.filename).toBe('product-security.md')
    expect(body.content_base64).toBeTruthy()
    vi.unstubAllGlobals()
  })

  it('allows replacing an existing profile when all three slots are occupied', async () => {
    const fullProfile = {
      ...profile,
      available: ['security-consulting', 'research', 'product'],
    }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/api/token')) {
        return { ok: true, json: async () => ({ token: 'local-token' }) } as Response
      }
      return { ok: false, json: async () => ({}) } as Response
    }))
    renderSettings({ profile: fullProfile })
    const file = new File(['# Updated'], 'updated.md', { type: 'text/markdown' })
    await screen.findByLabelText('Profile name')
    fireEvent.change(screen.getByLabelText('Resume file'), { target: { files: [file] } })

    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'fourth' } })
    expect(screen.getByRole('button', { name: 'Build profile' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'research' } })
    expect(screen.getByRole('button', { name: 'Build profile' })).toBeEnabled()
    vi.unstubAllGlobals()
  })

  it('scrolls between settings sections without replacing the route hash', () => {
    const scrollIntoView = vi.spyOn(HTMLElement.prototype, 'scrollIntoView')
    location.hash = '#/?view=settings'
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: 'Data sync' }))
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(location.hash).toBe('#/?view=settings')
    scrollIntoView.mockRestore()
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
