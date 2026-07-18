// Settings for local search profiles, display preferences, data freshness, and
// snapshot privacy. Profile mutations are available only through local serve.

import { useState } from 'react'
import type { ReactNode } from 'react'
import { Download, FileText, GitBranch, Lock, Palette, RefreshCw, Shield, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Badge, Button, Chip, Segmented } from '@/ui'
import { useScoreFormat } from '@/hooks/useScoreFormat'
import { connectToken, disconnectToken, hasGitHubToken, pullLatestData, scanNewMail } from '@/lib/refresh'
import { profileReset, profileUpdate, profileUpload, profileUse } from '@/lib/outreach'
import { fmtGenerated } from '@/lib/format'
import type { Profile } from '@/lib/schema'

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
  const [profileName, setProfileName] = useState('')
  const [uploading, setUploading] = useState(false)
  const locations = prof ? [...new Set([...prof.locations, ...(prof.remote ? ['Remote'] : [])])] : []

  const switchProfile = async (name: string) => {
    if (!serveToken || !prof || name === prof.name) return
    setSwitching(true)
    try {
      const res = await profileUse(name, serveToken)
      if (res.ok && res.profile) {
        onProfileChange?.(res.profile)
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
        setProfileName('')
        toast.success(`Profile built: ${res.profile.name}`)
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
      <header className="border-b border-line px-5 py-5 sm:px-7">
        <p className="text-[10px] font-semibold uppercase text-ink-3">Settings</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-ink">Workspace preferences</h2>
            <p className="mt-1 text-[13px] text-ink-3">Search profile, local display preferences, sync, and session privacy.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {serveToken !== undefined && (
              <Badge tone={serveToken ? 'good' : 'neutral'}>{serveToken ? 'Local workspace' : 'Published snapshot'}</Badge>
            )}
            <p className="text-[12px] text-ink-3">{total} {total === 1 ? 'role' : 'roles'} · updated {fmtGenerated(generated)}</p>
          </div>
        </div>
      </header>

      <div className="grid lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="border-b border-line bg-inset/35 p-4 lg:border-b-0 lg:border-r lg:p-5">
          <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto [scrollbar-width:none] lg:sticky lg:top-4 lg:flex-col [&::-webkit-scrollbar]:hidden">
            <SettingsLink target="appearance" icon={<Palette size={14} aria-hidden="true" />}>Appearance</SettingsLink>
            <SettingsLink target="profile" icon={<FileText size={14} aria-hidden="true" />}>Search profiles</SettingsLink>
            <SettingsLink target="sync" icon={<RefreshCw size={14} aria-hidden="true" />}>Data sync</SettingsLink>
            {onLock && <SettingsLink target="privacy" icon={<Shield size={14} aria-hidden="true" />}>Privacy</SettingsLink>}
          </nav>
        </aside>

        <div className="min-w-0">
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
              <div className="flex flex-wrap items-center justify-between gap-3 pb-5">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-semibold text-ink">{prof.resume}</span>
                    {prof.seniority && <Badge tone="brand">{prof.seniority}</Badge>}
                    {prof.years_experience > 0 && <span className="text-[12px] text-ink-3">{prof.years_experience} yrs</span>}
                  </div>
                  <p className="mt-1 text-[12px] text-ink-3">Active ranking résumé</p>
                </div>
            {serveToken && prof.available.length > 1 && (
                <select
                  value={prof.name}
                  onChange={(e) => void switchProfile(e.target.value)}
                  disabled={switching}
                  aria-label="Active search profile"
                  className="h-9 rounded-md border border-line bg-inset px-3 text-[13px] text-ink outline-none focus:border-line-strong disabled:opacity-50"
                >
                  {prof.available.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
            )}
              </div>
            {prof.search_terms.length > 0 && (
                <TagField label="Target roles">
                {prof.search_terms.map((t) => (
                  <Chip key={t}>{t}</Chip>
                ))}
                </TagField>
            )}
              {locations.length > 0 && (
                <TagField label="Locations">
                {locations.map((l) => (
                  <Chip key={l}>{l}</Chip>
                ))}
                </TagField>
            )}
            {prof.top_skills.length > 0 && (
                <TagField label="Top skills">
                {prof.top_skills.slice(0, 12).map((s) => (
                  <Chip key={s}>{s}</Chip>
                ))}
                </TagField>
            )}
            {serveToken && (
              <ProfileIntentEditor
                key={`${prof.name}:${prof.search_terms.join('|')}:${prof.locations.join('|')}:${prof.remote}`}
                profile={prof}
                token={serveToken}
                onChange={(next) => {
                  onProfileChange?.(next)
                }}
              />
            )}
                </>
              ) : (
                <p className="pb-5 text-[13px] text-ink-3">No search profile loaded.</p>
              )}

              {serveToken && (
                <div className="border-t border-line pt-5">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[13px] font-semibold text-ink">Upload résumé</p>
                      <p className="text-[11px] text-ink-3">{profileCount} of {profileLimit} profiles</p>
                    </div>
                    {profileCapReached && <Badge tone="neutral">Reuse a profile name to replace</Badge>}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-[minmax(10rem,.55fr)_minmax(12rem,1fr)_auto]">
                    <input
                      value={profileName}
                      onChange={(event) => setProfileName(event.target.value)}
                      aria-label="Profile name"
                      placeholder="Profile name"
                      className="h-9 rounded-md border border-line bg-inset px-3 text-[13px] text-ink outline-none focus:border-line-strong disabled:opacity-50"
                    />
                    <label className="flex h-9 min-w-0 cursor-pointer items-center gap-2 rounded-md border border-line bg-inset px-3 text-[12px] text-ink-2 hover:border-line-strong">
                      <Upload size={14} className="shrink-0" aria-hidden="true" />
                      <span className="truncate">{resumeFile?.name || 'Choose résumé'}</span>
                      <input
                        type="file"
                        accept=".md,.txt,.json,.pdf"
                        aria-label="Resume file"
                        onChange={(event) => {
                          const file = event.target.files?.[0] ?? null
                          setResumeFile(file)
                          if (file && !profileName) {
                            setProfileName(file.name.replace(/\.[^.]+$/, ''))
                          }
                        }}
                        className="sr-only"
                      />
                    </label>
                    <Button
                      variant="secondary"
                      disabled={newProfileBlocked || uploading || !resumeFile || !profileName.trim()}
                      onClick={() => void uploadResume()}
                    >
                      {uploading ? <RefreshCw size={15} className="animate-spin" aria-hidden="true" /> : <Upload size={15} aria-hidden="true" />}
                      Build profile
                    </Button>
                  </div>
                </div>
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
    <section id={id} className="scroll-mt-4 border-b border-line px-5 py-6 last:border-b-0 sm:px-7">
      <header className="mb-5 flex items-start gap-3">
        <span className="mt-0.5 text-ink-3">{icon}</span>
        <div>
          <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
          <p className="mt-0.5 text-[12px] text-ink-3">{description}</p>
        </div>
      </header>
      {children}
    </section>
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

function TagField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-t border-line py-4 last:pb-0">
      <div className="mb-2 text-[10px] font-semibold uppercase text-ink-3">
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
  const [locations, setLocations] = useState(profile.locations.join('\n'))
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
        locations: splitLines(locations),
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
          <Button variant="secondary" disabled={saving || resetting || !splitLines(roles).length || !splitLines(locations).length} onClick={() => void save()}>
            {saving ? <RefreshCw size={14} className="animate-spin" aria-hidden="true" /> : <FileText size={14} aria-hidden="true" />}
            Save profile
          </Button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-[10px] font-semibold uppercase text-ink-3">
          Target roles
          <textarea
            aria-label="Target roles"
            value={roles}
            onChange={(event) => setRoles(event.target.value)}
            rows={6}
            className="mt-1 w-full resize-y rounded-md border border-line bg-inset px-3 py-2 text-[13px] font-normal leading-5 normal-case text-ink outline-none focus:border-line-strong"
          />
        </label>
        <label className="text-[10px] font-semibold uppercase text-ink-3">
          Locations
          <textarea
            aria-label="Profile locations"
            value={locations}
            onChange={(event) => setLocations(event.target.value)}
            rows={6}
            className="mt-1 w-full resize-y rounded-md border border-line bg-inset px-3 py-2 text-[13px] font-normal leading-5 normal-case text-ink outline-none focus:border-line-strong"
          />
        </label>
      </div>
      <label className="mt-3 inline-flex items-center gap-2 text-[12px] text-ink-2">
        <input
          type="checkbox"
          checked={remote}
          onChange={(event) => setRemote(event.target.checked)}
          className="h-4 w-4 accent-[var(--brand-coral)]"
        />
        Include remote roles
      </label>
    </section>
  )
}
