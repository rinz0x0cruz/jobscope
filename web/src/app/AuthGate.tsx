import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Compass, Lock } from 'lucide-react'
import type { DashboardData, EncRef } from '@/lib/schema'
import { cacheUnlock, clearUnlock, readCachedUnlock, unlockDashboard } from '@/lib/unlock'
import { localDashboard, localServeToken } from '@/lib/outreach'
import { Button, Input } from '@/ui'

export interface AuthGateProps {
  /** Startup fallback. Local serve replaces it with live SQLite data; the
   *  published build contains an empty shell and remains locked. */
  baked: DashboardData
  /** Encrypted whole-site marker (lazy pointer or inline blob), or null. */
  encrypted: EncRef | null
  /** Rendered with the resolved data and a `lock` callback once access is granted. */
  children: (
    data: DashboardData,
    lock: () => void,
    source: 'baked' | 'local' | 'snapshot',
    localToken: string | null | undefined,
  ) => ReactNode
}

/**
 * Whole-app auth gate. Local serve replaces the startup payload through its
 * guarded runtime API. Pages bakes an empty shell, so nothing renders until the
 * AES-256-GCM snapshot is unlocked in-browser (cached per-tab in sessionStorage).
 */
export function AuthGate({ baked, encrypted, children }: AuthGateProps) {
  const openLocally = (baked.rows?.length ?? 0) > 0
  const [unlocked, setUnlocked] = useState<DashboardData | null>(() => readCachedUnlock())
  const [localSession, setLocalSession] = useState<{
    data: DashboardData
    token: string
  } | null>(null)
  const data = localSession?.data ?? (openLocally ? baked : unlocked)
  const source = localSession ? 'local' : (openLocally ? 'baked' : 'snapshot')

  useEffect(() => {
    let active = true
    void localServeToken()
      .then(async (token) => token ? { token, data: await localDashboard(token) } : null)
      .then((session) => {
        if (active && session) setLocalSession(session)
      })
      .catch(() => {
        // Static Pages and standalone builds intentionally have no local API.
      })
    return () => { active = false }
  }, [])

  const lock = () => {
    clearUnlock()
    setUnlocked(null)
  }

  const localToken = localSession?.token ?? (source === 'snapshot' ? null : undefined)
  if (data) return <>{children(data, lock, source, localToken)}</>
  return <LockScreen encrypted={encrypted} onUnlock={setUnlocked} />
}

function LockScreen({
  encrypted,
  onUnlock,
}: {
  encrypted: EncRef | null
  onUnlock: (data: DashboardData) => void
}) {
  const [pass, setPass] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!pass || busy || !encrypted) return
    setBusy(true)
    setError('')
    try {
      const data = await unlockDashboard(encrypted, pass)
      cacheUnlock(data)
      onUnlock(data)
    } catch {
      setError('Wrong passphrase, or the data could not be loaded.')
      setBusy(false)
      setPass('')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-6 font-sans text-ink">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-card bg-brand text-white">
            <Compass size={22} aria-hidden="true" />
          </span>
          <h1 className="font-display text-xl font-semibold text-ink">jobscope</h1>
          <p className="mt-1.5 inline-flex items-center gap-1.5 text-sm text-ink-3">
            <Lock size={13} aria-hidden="true" />
            This dashboard is locked
          </p>
        </div>

        {encrypted ? (
          <form onSubmit={submit} className="space-y-3">
            <Input
              type="password"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              placeholder="Passphrase"
              autoFocus
              disabled={busy}
              autoComplete="current-password"
              aria-label="Passphrase"
            />
            {error && (
              <p className="text-[13px]" style={{ color: 'var(--hot)' }}>
                {error}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              disabled={busy || !pass}
              className="w-full justify-center"
            >
              {busy ? 'Decrypting…' : 'Unlock'}
            </Button>
          </form>
        ) : (
          <p className="text-center text-sm text-ink-3">
            No encrypted data is available to unlock.
          </p>
        )}

        <p className="mt-4 text-center text-[12px] leading-relaxed text-ink-3">
          Everything is decrypted in your browser. Nothing is sent anywhere.
        </p>
      </div>
    </div>
  )
}
