import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { Settings } from '@/features/settings'
import type { SettingsProps } from '@/features/settings'
import { ScoreFormatProvider } from '@/hooks/ScoreFormatProvider'
import type { Profile } from '@/lib/schema'
import { atsCheck } from '@/lib/outreach'

// Only the ATS call is stubbed; every other client function stays real so the
// existing profile/sync tests are unaffected.
vi.mock('@/lib/outreach', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/outreach')>()),
  atsCheck: vi.fn(),
}))

const profile: Profile = {
  resume: 'security-consulting',
  seniority: 'Senior',
  years_experience: 8,
  search_terms: ['Security Engineer', 'AppSec'],
  locations: ['India'],
  remote: true,
  top_skills: ['Python', 'Threat Modeling'],
  name: 'security-consulting',
  available: ['security-consulting'],
}

function renderSettings(over: Partial<SettingsProps> = {}) {
  const onLock = vi.fn()
  render(
    <ScoreFormatProvider>
      <Settings profile={profile} generated="2026-07-02T10:00:00Z" total={42} serveToken={null} onLock={onLock} {...over} />
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
    expect(screen.getByRole('heading', { name: 'Résumé' })).toBeInTheDocument()
    const card = screen.getByRole('region', { name: 'Active search profile' })
    expect(screen.getAllByText('security-consulting')).toHaveLength(2)
    expect(within(card).getByText('Security Engineer')).toBeInTheDocument()
    expect(within(card).getByText('Threat Modeling')).toBeInTheDocument()
    expect(within(card).getByText('Active ranking profile')).toBeInTheDocument()
    expect(within(card).getByText('Preferred job regions')).toBeInTheDocument()
  })

  it('normalizes legacy city locations without country-name collisions', () => {
    renderSettings({
      profile: {
        ...profile,
        locations: ['Indianapolis, United States', 'London, UK', 'Berlin, Germany'],
      },
      serveToken: 'local-token',
    })

    expect(screen.getByRole('checkbox', { name: 'India' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'United States' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'United Kingdom' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Germany' })).toBeChecked()
  })

  it('updates the editor when fresher runtime profile data arrives', async () => {
    const view = render(
      <ScoreFormatProvider>
        <Settings profile={profile} generated="2026-07-02T10:00:00Z" total={42} serveToken={null} onLock={vi.fn()} />
      </ScoreFormatProvider>,
    )
    const fresh = { ...profile, search_terms: ['Cloud Security Engineer'] }
    view.rerender(
      <ScoreFormatProvider>
        <Settings profile={fresh} generated="2026-07-02T10:00:00Z" total={42} serveToken={null} onLock={vi.fn()} />
      </ScoreFormatProvider>,
    )
    expect(await screen.findByText('Cloud Security Engineer')).toBeInTheDocument()
    expect(screen.queryByText('AppSec')).not.toBeInTheDocument()
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

  it('delegates Gmail scanning to the workspace refresh handler', () => {
    const onRefresh = vi.fn()
    renderSettings({ onRefresh })
    fireEvent.click(screen.getByRole('button', { name: 'Scan Gmail' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('labels local serve as the editable workspace', () => {
    renderSettings({ serveToken: 'local-token' })
    expect(screen.getByText('Local workspace')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pull latest' })).not.toBeInTheDocument()
    expect(screen.getByText(/without rebuilding or publishing/)).toBeInTheDocument()
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
      if (url.endsWith('/api/resume/upload')) {
        return { ok: true, json: async () => ({ ok: true, profile: nextProfile, profile_count: 2, profile_limit: 3 }) } as Response
      }
      return { ok: false, json: async () => ({}) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderSettings({ onProfileChange, serveToken: 'local-token' })

    const name = await screen.findByLabelText('Profile name')
    expect(name).toHaveValue('security-consulting')
    fireEvent.change(name, { target: { value: 'product-security' } })
    const file = new File(['# Jane\n## Skills\nPython, AWS'], 'product-security.md', { type: 'text/markdown' })
    fireEvent.change(screen.getByLabelText('Resume file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Add résumé' }))

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
    renderSettings({ profile: fullProfile, serveToken: 'local-token' })
    const file = new File(['# Updated'], 'updated.md', { type: 'text/markdown' })
    expect(await screen.findByLabelText('Profile name')).toHaveValue('security-consulting')
    fireEvent.change(screen.getByLabelText('Resume file'), { target: { files: [file] } })

    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'fourth' } })
    expect(screen.getByRole('button', { name: 'Add résumé' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'research' } })
    expect(screen.getByRole('button', { name: 'Replace résumé' })).toBeEnabled()
    vi.unstubAllGlobals()
  })

  it('edits search intent without changing resume-derived facts', async () => {
    const onProfileChange = vi.fn()
    const edited = {
      ...profile,
      search_terms: ['Detection Engineer', 'Threat Researcher'],
      locations: ['Germany'],
      remote: false,
    }
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/api/profile') && init?.method === 'PUT') {
        return { ok: true, json: async () => ({ ok: true, profile: edited }) } as Response
      }
      return { ok: false, json: async () => ({}) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderSettings({ onProfileChange, serveToken: 'local-token' })

    fireEvent.change(await screen.findByLabelText('Target roles'), {
      target: { value: 'Detection Engineer\nThreat Researcher' },
    })
    fireEvent.click(screen.getByRole('checkbox', { name: 'India' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Germany' }))
    fireEvent.click(screen.getByLabelText('Include worldwide remote roles'))
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => expect(onProfileChange).toHaveBeenCalledWith(edited))
    const call = fetchMock.mock.calls.find(([url, init]) => (
      String(url).endsWith('/api/profile') && (init as RequestInit)?.method === 'PUT'
    ))
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      name: profile.name,
      search_terms: ['Detection Engineer', 'Threat Researcher'],
      locations: ['Germany'],
      remote: false,
    })
    expect(edited.top_skills).toEqual(profile.top_skills)
    vi.unstubAllGlobals()
  })

  it('allows remote-only intent and blocks a completely empty search', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ ok: true, profile: { ...profile, locations: [] } }),
    }) as Response)
    vi.stubGlobal('fetch', fetchMock)
    renderSettings({ serveToken: 'local-token' })

    fireEvent.click(screen.getByRole('checkbox', { name: 'India' }))
    const remote = screen.getByLabelText('Include worldwide remote roles')
    const save = screen.getByRole('button', { name: 'Save profile' })
    expect(save).toBeEnabled()
    fireEvent.click(remote)
    expect(save).toBeDisabled()
    fireEvent.click(remote)
    fireEvent.click(save)

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'PUT')
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toMatchObject({
      locations: [],
      remote: true,
    })
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

  it('hides the ATS parse check without a local serve session', () => {
    renderSettings({ serveToken: null })
    expect(screen.queryByRole('button', { name: /Check résumé/ })).not.toBeInTheDocument()
  })

  it('reports the ATS score and the formatting faults to fix', async () => {
    vi.mocked(atsCheck).mockResolvedValue({
      ok: true,
      report: {
        name: 'Ada Lovelace', email: 'ada@example.test', phone: '', location: 'Pune, India',
        seniority: 'senior', years: 8, skills: ['python', 'siem'], titles: ['Security Engineer'],
        score: 78,
        warnings: [
          { level: 'warn', code: 'no_phone', message: 'no phone number parsed', hint: 'add a plain-text phone line' },
          { level: 'error', code: 'image_pdf', message: 'resume looks image-based', hint: 'export a text-based PDF' },
        ],
      },
    })
    renderSettings({ serveToken: 'local-token' })
    fireEvent.click(screen.getByRole('button', { name: /Check résumé/ }))

    expect(await screen.findByText('78')).toBeInTheDocument()
    expect(screen.getByText('2 skills and 1 title parsed · ~8y')).toBeInTheDocument()
    expect(screen.getByText('no phone number parsed')).toBeInTheDocument()
    expect(screen.getByText('export a text-based PDF')).toBeInTheDocument()
    // an unparsed field is named rather than silently blank
    expect(screen.getByText('not parsed')).toBeInTheDocument()
    expect(vi.mocked(atsCheck)).toHaveBeenCalledWith('local-token')
  })
})
