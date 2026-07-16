// The Settings lens: appearance preferences (theme, score format), a read-only
// résumé-profile summary, and a session lock. Client-only — theme + score format
// persist to localStorage; nothing here mutates the dashboard data.

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Download, FileText, GitBranch, Lock, Palette, RefreshCw, Shield } from 'lucide-react'
import { toast } from 'sonner'
import { Badge, Button, Chip, Segmented } from '@/ui'
import { useScoreFormat } from '@/hooks/useScoreFormat'
import { connectToken, disconnectToken, hasGitHubToken, pullLatestData } from '@/lib/refresh'
import { localServeToken, profileUse } from '@/lib/outreach'
import { fmtGenerated } from '@/lib/format'
import type { Profile } from '@/lib/schema'

export interface SettingsProps {
  profile: Profile | null
  generated: string
  total: number
  onLock: () => void
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

export function Settings({ profile, generated, total, onLock }: SettingsProps) {
  const [theme, setTheme] = useState<'light' | 'dark'>(currentTheme)
  const { format, setFormat } = useScoreFormat()
  const [tokenConnected, setTokenConnected] = useState(hasGitHubToken)
  const [prof, setProf] = useState<Profile | null>(profile)
  const [serveToken, setServeToken] = useState<string | null>(null)
  const [switching, setSwitching] = useState(false)
  const locations = prof ? [...new Set([...prof.locations, ...(prof.remote ? ['Remote'] : [])])] : []

  useEffect(() => {
    let live = true
    localServeToken().then((t) => live && setServeToken(t))
    return () => {
      live = false
    }
  }, [])

  const switchProfile = async (name: string) => {
    if (!serveToken || !prof || name === prof.name) return
    setSwitching(true)
    try {
      const res = await profileUse(name, serveToken)
      if (res.ok && res.profile) {
        setProf(res.profile)
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

  return (
    <section className="mx-auto min-h-full w-full max-w-[1600px] border-x border-line bg-panel">
      <header className="border-b border-line px-5 py-5 sm:px-7">
        <p className="text-[10px] font-semibold uppercase text-ink-3">Settings</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-ink">Workspace preferences</h2>
            <p className="mt-1 text-[13px] text-ink-3">Search profile, local display preferences, sync, and session privacy.</p>
          </div>
          <p className="text-[12px] text-ink-3">{total} {total === 1 ? 'role' : 'roles'} · updated {fmtGenerated(generated)}</p>
        </div>
      </header>

      <div className="grid lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="border-b border-line bg-inset/35 p-4 lg:border-b-0 lg:border-r lg:p-5">
          <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto [scrollbar-width:none] lg:sticky lg:top-4 lg:flex-col [&::-webkit-scrollbar]:hidden">
            <SettingsLink target="appearance" icon={<Palette size={14} aria-hidden="true" />}>Appearance</SettingsLink>
            {prof && <SettingsLink target="profile" icon={<FileText size={14} aria-hidden="true" />}>Search profile</SettingsLink>}
            <SettingsLink target="sync" icon={<RefreshCw size={14} aria-hidden="true" />}>Data sync</SettingsLink>
            <SettingsLink target="privacy" icon={<Shield size={14} aria-hidden="true" />}>Privacy</SettingsLink>
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

          {prof && (
            <SettingsSection
              id="profile"
              icon={<FileText size={16} aria-hidden="true" />}
              title="Search profile"
              description="The résumé and targets used to rank incoming roles."
            >
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
            </SettingsSection>
          )}

          <SettingsSection
            id="sync"
            icon={<RefreshCw size={16} aria-hidden="true" />}
            title="Data sync"
            description="Run the GitHub refresh workflow or pull its latest encrypted result."
          >
            <div className="flex flex-wrap items-center gap-2">
            {tokenConnected ? (
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
            )}
            <Button variant="ghost" onClick={() => void pullLatestData()}>
              <Download size={15} aria-hidden="true" />
              Pull latest
            </Button>
            </div>
            <p className="mt-3 text-[12px] text-ink-3">
              The optional token is stored only in this browser and requires GitHub Actions write access.
            </p>
          </SettingsSection>

          <SettingsSection
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
          </SettingsSection>
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
