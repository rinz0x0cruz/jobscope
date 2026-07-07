import { useState, type FormEvent } from 'react'
import { Lock } from 'lucide-react'
import type { DashboardData, EncRef } from '@/lib/schema'
import { cacheUnlock, unlockDashboard } from '@/lib/unlock'

/**
 * Passphrase form that fetches + decrypts the full un-redacted dashboard in the
 * browser and hands it up via `onUnlock`. Shared by the header lock dialog and
 * the Applications tab gate. Nothing is ever sent anywhere.
 */
export function UnlockForm({
  blob,
  onUnlock,
  autoFocus = true,
}: {
  blob: EncRef
  onUnlock: (data: DashboardData) => void
  autoFocus?: boolean
}) {
  const [pass, setPass] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!pass || busy) return
    setBusy(true)
    setError('')
    try {
      const data = await unlockDashboard(blob, pass)
      cacheUnlock(data)
      onUnlock(data)
    } catch {
      setError('Wrong passphrase, or the data could not be loaded.')
      setBusy(false)
      setPass('')
    }
  }

  return (
    <form onSubmit={submit} className="w-full space-y-3.5 text-center">
      <div className="flex items-center justify-center gap-2 text-sm font-semibold text-fg">
        <Lock size={15} />
        Unlock the full dashboard
      </div>
      <p className="text-[13px] text-mute">
        Enter your passphrase to reveal the un-redacted data — job descriptions, match rationale,
        referral contacts, and applications. Everything is decrypted in your browser; nothing is sent
        anywhere.
      </p>
      <input
        type="password"
        value={pass}
        onChange={(e) => setPass(e.target.value)}
        placeholder="Passphrase"
        autoFocus={autoFocus}
        disabled={busy}
        autoComplete="current-password"
        className="w-full rounded-[10px] border border-border bg-bg2 px-3 py-2 text-sm text-fg outline-none transition focus:border-border-h"
      />
      {error && (
        <p className="text-xs" style={{ color: '#ef4444' }}>
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !pass}
        className="w-full rounded-[10px] border border-border bg-bg2 px-4 py-2 text-sm font-semibold text-fg transition hover:border-border-h disabled:opacity-50"
      >
        {busy ? 'Decrypting…' : 'Unlock'}
      </button>
    </form>
  )
}
