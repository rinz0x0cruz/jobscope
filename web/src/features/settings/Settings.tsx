// The Settings lens: appearance preferences (theme, score format), a read-only
// résumé-profile summary, and a session lock. Client-only — theme + score format
// persist to localStorage; nothing here mutates the dashboard data.

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Lock } from 'lucide-react'
import { toast } from 'sonner'
import { Badge, Button, Card, Chip, Segmented } from '@/ui'
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
    <div className="mx-auto max-w-2xl space-y-5">
      <Card title="Appearance">
        <div className="divide-y divide-line">
          <Row label="Theme" hint="Warm light or dark surfaces.">
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
          </Row>
          <Row label="Match score" hint="Show the 0–100 fit number or an A–F grade.">
            <Segmented
              ariaLabel="Match score format"
              value={format}
              onChange={(v) => setFormat(v === 'grade' ? 'grade' : 'number')}
              options={[
                { value: 'number', label: 'Number' },
                { value: 'grade', label: 'Grade' },
              ]}
            />
          </Row>
        </div>
      </Card>

      {prof && (
        <Card title="Résumé profile">
          <div className="space-y-3 text-sm">
            {serveToken && prof.available.length > 1 && (
              <Field label="Active profile">
                <select
                  value={prof.name}
                  onChange={(e) => void switchProfile(e.target.value)}
                  disabled={switching}
                  aria-label="Active search profile"
                  className="rounded-lg border border-line bg-inset px-2 py-1 text-[13px] text-ink outline-none focus:border-line-strong disabled:opacity-50"
                >
                  {prof.available.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
                <span className="text-ink-3">drives your next scan</span>
              </Field>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-ink">{prof.resume}</span>
              {prof.seniority && <Badge tone="brand">{prof.seniority}</Badge>}
              {prof.years_experience > 0 && (
                <span className="text-ink-3">{prof.years_experience} yrs</span>
              )}
            </div>
            {prof.search_terms.length > 0 && (
              <Field label="Searching for">
                {prof.search_terms.map((t) => (
                  <Chip key={t}>{t}</Chip>
                ))}
              </Field>
            )}
            {prof.locations.length > 0 && (
              <Field label="Locations">
                {prof.locations.map((l) => (
                  <Chip key={l}>{l}</Chip>
                ))}
                {prof.remote && <Chip>Remote</Chip>}
              </Field>
            )}
            {prof.top_skills.length > 0 && (
              <Field label="Top skills">
                {prof.top_skills.slice(0, 12).map((s) => (
                  <Chip key={s}>{s}</Chip>
                ))}
              </Field>
            )}
          </div>
        </Card>
      )}

      <Card title="Sync">
        <div className="space-y-3 text-sm">
          <p className="text-ink-2">
            Refresh scans your mailbox via the{' '}
            <code className="rounded bg-inset px-1 py-0.5 text-[12px]">refresh.yml</code> Action,
            then pulls the freshly published results. Connect a fine-grained GitHub token (Actions:
            write) for one-tap scans — it’s stored only in this browser.
          </p>
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
                Connect GitHub token
              </Button>
            )}
            <Button variant="ghost" onClick={() => void pullLatestData()}>
              Pull latest
            </Button>
          </div>
        </div>
      </Card>

      <Card title="Session">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-ink-2">
            Lock the dashboard and clear the decrypted data from this tab.
          </p>
          <Button variant="secondary" onClick={onLock} className="shrink-0">
            <Lock size={15} aria-hidden="true" />
            Lock
          </Button>
        </div>
      </Card>

      <p className="text-center text-[12px] text-ink-3">
        {total} {total === 1 ? 'role' : 'roles'} · updated {fmtGenerated(generated)}
      </p>
    </div>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <div className="text-sm font-medium text-ink">{label}</div>
        {hint && <div className="text-[12px] text-ink-3">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  )
}
