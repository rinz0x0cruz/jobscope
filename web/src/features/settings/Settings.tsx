// Settings for local search profiles, display preferences, data freshness, and
// snapshot privacy. Profile mutations are available only through local serve.

import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown, Download, FileText, GitBranch, Lock, Palette, RefreshCw, Shield, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Badge, Button, Chip, Segmented, WorkspaceHeader } from '@/ui'
import { useScoreFormat } from '@/hooks/useScoreFormat'
import { connectToken, disconnectToken, hasGitHubToken, pullLatestData, scanNewMail } from '@/lib/refresh'
import { profileReset, profileUpdate, profileUpload, profileUse } from '@/lib/outreach'
import { fmtGenerated } from '@/lib/format'
import type { Profile } from '@/lib/schema'

const JOB_MARKET_GROUPS = [
  { label: 'South Asia', markets: ['India'] },
  { label: 'Asia Pacific', markets: ['Singapore', 'Japan', 'Australia'] },
  { label: 'Europe', markets: ['United Kingdom', 'Germany', 'France', 'Netherlands', 'Ireland'] },
  { label: 'North America', markets: ['United States', 'Canada'] },
  { label: 'Middle East', markets: ['United Arab Emirates'] },
] as const

const JOB_MARKETS = JOB_MARKET_GROUPS.flatMap(({ markets }) => markets)

function canonicalJobMarket(value: string): string | null {
  const normalized = value.trim().toLowerCase().replace(/\s+/g, ' ')
  if (!normalized || normalized === 'remote') return null
  const exact = JOB_MARKETS.find((market) => market.toLowerCase() === normalized)
  if (exact) return exact
  const contained = JOB_MARKETS.find((market) => (
    new RegExp(`\\b${market.toLowerCase()}\\b`).test(normalized)
  ))
  if (contained) return contained
  if (/\busa?\b/.test(normalized)) return 'United States'
  if (/\buk\b/.test(normalized)) return 'United Kingdom'
  if (/\buae\b/.test(normalized)) return 'United Arab Emirates'
  return null
}

function preferredJobMarkets(locations: string[]): string[] {
  const selected = locations
    .map(canonicalJobMarket)
    .filter((market): market is string => Boolean(market))
  return [...new Set(selected)]
}

export interface SettingsProps {
  profile: Profile | null
  generated: string
  total: number
  serveToken: string | null | undefined
  onLock?: () => void
  onRefresh?: () => void
  onProfileChange?: (profile: Profile) => void
}

function currentTheme(): 'light' | 'dark' {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains('light') ? 'light' : 'dark'
}

function applyTheme(theme: 'light' | 'dark') {
  const el = document.documentElement
  el.classList.remove('dark', 'light')
  el.classList.add(theme)
  try {
    localStorage.setItem('jobscope-theme', theme)
  } catch {
    /* private mode — the choice still applies for this session */
  }
}

export function Settings({ profile, generated, total, serveToken, onLock, onRefresh, onProfileChange }: SettingsProps) {
  const [theme, setTheme] = useState<'light' | 'dark'>(currentTheme)
  const { format, setFormat } = useScoreFormat()
  const [tokenConnected, setTokenConnected] = useState(hasGitHubToken)
  const prof = profile
  const [switching, setSwitching] = useState(false)
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [profileName, setProfileName] = useState(profile?.name ?? '')
  const [uploading, setUploading] = useState(false)
  const jobMarkets = prof ? preferredJobMarkets(prof.locations) : []

  const switchProfile = async (name: string) => {
    if (!serveToken || !prof || name === prof.name) return
    setSwitching(true)
    try {
      const res = await profileUse(name, serveToken)
      if (res.ok && res.profile) {
        onProfileChange?.(res.profile)
        setProfileName(res.profile.name)
        toast.success(`Active profile: ${name}`)
      } else {
        toast.error(res.error || 'Could not switch profile')
      }
    } catch {
      toast.error('Could not reach jobscope serve.')
    } finally {
      setSwitching(false)
    }
  }

  const uploadResume = async () => {
    if (!serveToken || !resumeFile || !profileName.trim()) return
    setUploading(true)
    try {
      const res = await profileUpload(resumeFile, profileName.trim(), serveToken)
      if (res.ok && res.profile) {
        onProfileChange?.(res.profile)
        setResumeFile(null)
        setProfileName(res.profile.name)
        toast.success(`Résumé updated: ${res.profile.name}`)
      } else {
        toast.error(res.error || 'Could not build profile')
      }
    } catch {
      toast.error('Could not upload resume')
    } finally {
      setUploading(false)
    }
  }

  const profileCount = prof?.available.length ?? 0
  const profileLimit = 3
  const profileCapReached = profileCount >= profileLimit
  const normalizedProfileName = profileName.trim().toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const replacingProfile = Boolean(
    normalizedProfileName && prof?.available.includes(normalizedProfileName),
  )
  const newProfileBlocked = profileCapReached && !replacingProfile

  return (
    <section className="mx-auto min-h-full w-full max-w-[1600px] border-x border-line bg-panel">
      <WorkspaceHeader
        eyebrow="System"
        title="Settings"
        description="Search profiles, local display preferences, data sync, and session privacy."
        actions={(
          <>
            {serveToken !== undefined && (
              <Badge tone={serveToken ? 'good' : 'neutral'}>{serveToken ? 'Local workspace' : 'Published snapshot'}</Badge>
            )}
            <p className="text-[12px] text-ink-3">{total} {total === 1 ? 'role' : 'roles'} · updated {fmtGenerated(generated)}</p>
          </>
        )}
      />

      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="min-w-0 border-b border-line bg-inset/35 p-4 lg:border-b-0 lg:border-r lg:p-5">
          <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto [scrollbar-width:none] lg:sticky lg:top-4 lg:flex-col [&::-webkit-scrollbar]:hidden">
            <SettingsLink target="resume" icon={<Upload size={14} aria-hidden="true" />}>Résumé</SettingsLink>
            <SettingsLink target="profile" icon={<FileText size={14} aria-hidden="true" />}>Search profiles</SettingsLink>
            <SettingsLink target="appearance" icon={<Palette size={14} aria-hidden="true" />}>Appearance</SettingsLink>
            <SettingsLink target="sync" icon={<RefreshCw size={14} aria-hidden="true" />}>Data sync</SettingsLink>
            {onLock && <SettingsLink target="privacy" icon={<Shield size={14} aria-hidden="true" />}>Privacy</SettingsLink>}
          </nav>
        </aside>

        <div className="min-w-0">
          <SettingsSection
            id="resume"
            icon={<Upload size={16} aria-hidden="true" />}
            title="Résumé"
            description="Replace the active ranking résumé or add another search profile."
          >
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[13px] font-semibold text-ink">{prof?.resume || 'No résumé loaded'}</p>
                <p className="mt-0.5 text-[11px] text-ink-3">
                  {serveToken ? 'Choose a PDF, Markdown, text, or JSON résumé.' : 'Résumé changes require the local workspace.'}
                </p>
              </div>
              <Badge tone="neutral">{profileCount} of {profileLimit} profiles</Badge>
            </div>
            {serveToken && (
              <div className="grid gap-2 sm:grid-cols-[minmax(10rem,.55fr)_minmax(12rem,1fr)_auto]">
                <input
                  value={profileName}
                  onChange={(event) => setProfileName(event.target.value)}
                  aria-label="Profile name"
                  placeholder="Profile name"
                  className="h-10 rounded-md border border-line bg-inset px-3 text-[13px] text-ink outline-none focus:border-line-strong"
                />
                <label className="flex h-10 min-w-0 cursor-pointer items-center gap-2 rounded-md border border-brand bg-brand-weak px-3 text-[12px] font-medium text-brand hover:border-line-strong">
                  <Upload size={15} className="shrink-0" aria-hidden="true" />
                  <span className="truncate">{resumeFile?.name || 'Choose résumé file'}</span>
                  <input
                    type="file"
                    accept=".md,.txt,.json,.pdf"
                    aria-label="Resume file"
                    onChange={(event) => {
                      const file = event.target.files?.[0] ?? null
                      setResumeFile(file)
                      if (file && !profileName) setProfileName(file.name.replace(/\.[^.]+$/, ''))
                    }}
                    className="sr-only"
                  />
                </label>
                <Button
                  variant="primary"
                  disabled={newProfileBlocked || uploading || !resumeFile || !profileName.trim()}
                  onClick={() => void uploadResume()}
                >
                  {uploading ? <RefreshCw size={15} className="animate-spin" aria-hidden="true" /> : <Upload size={15} aria-hidden="true" />}
                  {replacingProfile ? 'Replace résumé' : 'Add résumé'}
                </Button>
              </div>
            )}
            {profileCapReached && !replacingProfile && (
              <p className="mt-2 text-[11px] text-ink-3">Reuse an existing profile name to replace its résumé.</p>
            )}
          </SettingsSection>

          <SettingsSection
            id="appearance"
            icon={<Palette size={16} aria-hidden="true" />}
            title="Appearance"
            description="Choose how match information is displayed in this browser."
          >
            <PreferenceRow label="Theme" hint="Light or dark workspace surfaces.">
            <Segmented
              ariaLabel="Theme"
              value={theme}
              onChange={(v) => {
                const t = v === 'dark' ? 'dark' : 'light'
                setTheme(t)
                applyTheme(t)
              }}
              options={[
                { value: 'light', label: 'Light' },
                { value: 'dark', label: 'Dark' },
              ]}
            />
            </PreferenceRow>
            <PreferenceRow label="Match score" hint="Use the 0–100 fit number or an A–F grade.">
            <Segmented
              ariaLabel="Match score format"
              value={format}
              onChange={(v) => setFormat(v === 'grade' ? 'grade' : 'number')}
              options={[
                { value: 'number', label: 'Number' },
                { value: 'grade', label: 'Grade' },
              ]}
            />
            </PreferenceRow>
          </SettingsSection>

          <SettingsSection
              id="profile"
              icon={<FileText size={16} aria-hidden="true" />}
              title="Search profiles"
              description="The résumé and targets used to rank incoming roles."
            >
              {prof ? (
                <>
              <section
                aria-label="Active search profile"
                className="overflow-hidden rounded-card border border-line bg-panel shadow-[var(--shadow-panel)]"
              >
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-inset/35 px-4 py-4 sm:px-5">
                  <div className="flex min-w-0 items-center gap-3">
                    <span aria-hidden="true" className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-brand-weak font-display text-base font-semibold text-brand">
                      {(prof.name || prof.resume).slice(0, 1).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-[15px] font-semibold text-ink">{prof.name}</span>
                        {prof.seniority && <Badge tone="brand">{prof.seniority}</Badge>}
                        {prof.years_experience > 0 && <span className="font-mono text-[11px] text-ink-3">{prof.years_experience} yrs</span>}
                      </div>
                      <p className="mt-0.5 text-[11px] text-ink-3">
                        Active ranking profile{prof.resume !== prof.name ? ` · ${prof.resume} résumé` : ''}
                      </p>
                    </div>
                  </div>
                  {serveToken && prof.available.length > 1 && (
                    <select
                      value={prof.name}
                      onChange={(e) => void switchProfile(e.target.value)}
                      disabled={switching}
                      aria-label="Active search profile"
                      className="h-9 w-full rounded-md border border-line bg-panel px-3 text-[13px] text-ink outline-none focus:border-line-strong disabled:opacity-50 sm:w-auto sm:min-w-36"
                    >
                      {prof.available.map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <div className="divide-y divide-line">
                  {prof.search_terms.length > 0 && (
                    <ProfileFact label="Target roles">
                      {prof.search_terms.map((t) => (
                        <Chip key={t}>{t}</Chip>
                      ))}
                    </ProfileFact>
                  )}
                  {jobMarkets.length > 0 && (
                    <ProfileFact label="Preferred job regions">
                      {jobMarkets.map((market) => (
                        <Chip key={market}>{market}</Chip>
                      ))}
                    </ProfileFact>
                  )}
                  <ProfileFact label="Work mode">
                    <Chip>{prof.remote ? 'Worldwide remote included' : 'On-site and hybrid only'}</Chip>
                  </ProfileFact>
                  {prof.top_skills.length > 0 && (
                    <ProfileFact label="Top skills">
                      {prof.top_skills.slice(0, 12).map((s) => (
                        <Chip key={s}>{s}</Chip>
                      ))}
                    </ProfileFact>
                  )}
                </div>
              </section>
            {serveToken && (
              <div className="mt-5">
                <ProfileIntentEditor
                  key={`${prof.name}:${prof.search_terms.join('|')}:${prof.locations.join('|')}:${prof.remote}`}
                  profile={prof}
                  token={serveToken}
                  onChange={(next) => {
                    onProfileChange?.(next)
                  }}
                />
              </div>
            )}
                </>
              ) : (
                <p className="pb-5 text-[13px] text-ink-3">No search profile loaded.</p>
              )}

            </SettingsSection>

          <SettingsSection
            id="sync"
            icon={<RefreshCw size={16} aria-hidden="true" />}
            title="Data sync"
            description={serveToken
              ? 'Refresh the local SQLite workspace immediately. Publishing remains a separate operation.'
              : 'Run the GitHub refresh workflow or pull its latest encrypted snapshot.'}
          >
            <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={() => {
              if (onRefresh) onRefresh()
              else void scanNewMail()
            }}>
              <RefreshCw size={15} aria-hidden="true" />
              Scan Gmail
            </Button>
            {!serveToken && (tokenConnected ? (
              <>
                <Badge tone="good">Token connected</Badge>
                <Button
                  variant="secondary"
                  onClick={() => {
                    disconnectToken()
                    setTokenConnected(false)
                  }}
                >
                  <GitBranch size={15} aria-hidden="true" />
                  Disconnect
                </Button>
              </>
            ) : (
              <Button
                variant="secondary"
                onClick={() => {
                  connectToken()
                  setTokenConnected(hasGitHubToken())
                }}
              >
                <GitBranch size={15} aria-hidden="true" />
                Connect GitHub token
              </Button>
            ))}
            {!serveToken && <Button variant="ghost" onClick={() => void pullLatestData()}>
              <Download size={15} aria-hidden="true" />
              Pull latest
            </Button>}
            </div>
            <p className="mt-3 text-[12px] text-ink-3">
              {serveToken
                ? 'Local edits and scans update this workspace without rebuilding or publishing the site.'
                : 'The optional token is stored only in this browser and requires GitHub Actions write access.'}
            </p>
          </SettingsSection>

          {onLock && <SettingsSection
            id="privacy"
            icon={<Shield size={16} aria-hidden="true" />}
            title="Privacy"
            description="Control decrypted data held by the current browser tab."
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-[14px] font-medium text-ink">Lock this session</p>
                <p className="mt-0.5 text-[12px] text-ink-3">Clear decrypted dashboard data from memory and return to the passphrase screen.</p>
              </div>
              <Button variant="secondary" onClick={onLock} className="shrink-0">
                <Lock size={15} aria-hidden="true" />
                Lock
              </Button>
            </div>
          </SettingsSection>}
        </div>
      </div>
    </section>
  )
}

function SettingsLink({ target, icon, children }: { target: string; icon: ReactNode; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={() => document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
      className="flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-[12px] font-medium text-ink-2 transition-colors hover:bg-panel hover:text-ink"
    >
      {icon}{children}
    </button>
  )
}

function SettingsSection({ id, icon, title, description, children }: { id: string; icon: ReactNode; title: string; description: string; children: ReactNode }) {
  return (
    <details id={id} open className="group scroll-mt-4 border-b border-line px-5 py-1 last:border-b-0 sm:px-7 lg:py-6">
      <summary className="flex cursor-pointer list-none items-start gap-3 py-4 marker:hidden lg:py-0 [&::-webkit-details-marker]:hidden">
        <span className="mt-0.5 text-ink-3">{icon}</span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
          <p className="mt-0.5 text-[12px] text-ink-3">{description}</p>
        </div>
        <ChevronDown size={16} className="mt-1 text-ink-3 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="pb-5 lg:pb-0 lg:pt-5">{children}</div>
    </details>
  )
}

function PreferenceRow({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <div className="text-sm font-medium text-ink">{label}</div>
        {hint && <div className="text-[12px] text-ink-3">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

function ProfileFact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-2 px-4 py-3 sm:grid-cols-[7.5rem_minmax(0,1fr)] sm:px-5">
      <div className="pt-0.5 text-[11px] font-semibold text-ink-3">
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  )
}

function ProfileIntentEditor({
  profile,
  token,
  onChange,
}: {
  profile: Profile
  token: string
  onChange: (profile: Profile) => void
}) {
  const [roles, setRoles] = useState(profile.search_terms.join('\n'))
  const [markets, setMarkets] = useState(() => preferredJobMarkets(profile.locations))
  const [remote, setRemote] = useState(profile.remote)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const splitLines = (value: string) => value
    .split(/\r?\n/).map((item) => item.trim()).filter(Boolean)

  const save = async () => {
    setSaving(true)
    try {
      const result = await profileUpdate(profile.name, token, {
        search_terms: splitLines(roles),
        locations: markets,
        remote,
      })
      if (!result.ok || !result.profile) throw new Error(result.error || 'Could not save profile')
      onChange(result.profile)
      toast.success('Search profile saved')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save profile')
    } finally {
      setSaving(false)
    }
  }

  const reset = async () => {
    setResetting(true)
    try {
      const result = await profileReset(profile.name, token)
      if (!result.ok || !result.profile) throw new Error(result.error || 'Could not reset profile')
      onChange(result.profile)
      toast.success('Search intent reset from résumé')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not reset profile')
    } finally {
      setResetting(false)
    }
  }

  return (
    <section className="border-t border-line py-5" aria-label="Edit search intent">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-[13px] font-semibold text-ink">Search intent</h4>
          <p className="mt-0.5 text-[11px] text-ink-3">These fields drive scanning; résumé facts above remain derived.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" disabled={saving || resetting} onClick={() => void reset()}>
            <RefreshCw size={14} aria-hidden="true" /> Reset from résumé
          </Button>
          <Button variant="secondary" disabled={saving || resetting || !splitLines(roles).length || (!markets.length && !remote)} onClick={() => void save()}>
            {saving ? <RefreshCw size={14} className="animate-spin" aria-hidden="true" /> : <FileText size={14} aria-hidden="true" />}
            Save profile
          </Button>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
        <label className="text-[11px] font-semibold text-ink-3">
          Target roles
          <textarea
            aria-label="Target roles"
            value={roles}
            onChange={(event) => setRoles(event.target.value)}
            rows={6}
            className="mt-1 w-full resize-y rounded-md border border-line bg-inset px-3 py-2 text-[13px] font-normal leading-5 normal-case text-ink outline-none focus:border-line-strong"
          />
        </label>
        <fieldset className="min-w-0" aria-label="Preferred job regions">
          <legend className="text-[11px] font-semibold text-ink-3">Preferred job regions</legend>
          <p className="mt-0.5 text-[11px] text-ink-3">Choose one or more job markets. Each runs as a separate search.</p>
          <div className="mt-2 grid gap-x-4 gap-y-3 sm:grid-cols-2">
            {JOB_MARKET_GROUPS.map((group) => (
              <div key={group.label}>
                <p className="mb-1 text-[10px] font-medium text-ink-3">{group.label}</p>
                <div className="space-y-1">
                  {group.markets.map((market) => (
                    <label key={market} className="flex min-h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-[12px] text-ink-2 hover:bg-inset">
                      <input
                        type="checkbox"
                        checked={markets.includes(market)}
                        onChange={() => setMarkets((current) => (
                          current.includes(market)
                            ? current.filter((value) => value !== market)
                            : [...current, market]
                        ))}
                        className="h-4 w-4 accent-[var(--brand-coral)]"
                      />
                      {market}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </fieldset>
      </div>
      <label className="mt-3 inline-flex items-center gap-2 text-[12px] text-ink-2">
        <input
          type="checkbox"
          checked={remote}
          onChange={(event) => setRemote(event.target.checked)}
          className="h-4 w-4 accent-[var(--brand-coral)]"
        />
        Include worldwide remote roles
      </label>
    </section>
  )
}
