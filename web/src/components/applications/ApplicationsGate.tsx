import { useState, type FormEvent } from 'react'
import { Lock } from 'lucide-react'
import type { Application, EncBlob } from '@/lib/schema'

// sessionStorage key so an unlock survives tab switches within the same tab,
// but is cleared when the browser tab closes (never persisted to disk).
export const UNLOCK_KEY = 'jobscope:apps'

function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

/**
 * Decrypt the AES-256-GCM applications blob in-browser (mirrors
 * scripts/apps-template.html / build-secure-apps.mjs): PBKDF2-SHA256 derives a
 * 256-bit key from the passphrase, then AES-GCM decrypts the ciphertext.
 * Throws on a wrong passphrase (GCM tag mismatch).
 */
async function decryptBlob(blob: EncBlob, passphrase: string): Promise<Application[]> {
  const enc = new TextEncoder()
  const baseKey = await crypto.subtle.importKey('raw', enc.encode(passphrase), 'PBKDF2', false, ['deriveKey'])
  const key = await crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: b64ToBytes(blob.salt), iterations: blob.iter, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt'],
  )
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64ToBytes(blob.iv) }, key, b64ToBytes(blob.ct))
  const data = JSON.parse(new TextDecoder().decode(pt)) as { applications?: Application[] }
  return data.applications ?? []
}

/** Passphrase form shown in the Applications tab when the data is encrypted. */
export function ApplicationsGate({ blob, onUnlock }: { blob: EncBlob; onUnlock: (apps: Application[]) => void }) {
  const [pass, setPass] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!pass || busy) return
    setBusy(true)
    setError('')
    try {
      const apps = await decryptBlob(blob, pass)
      try {
        sessionStorage.setItem(UNLOCK_KEY, JSON.stringify(apps))
      } catch {
        // sessionStorage may be unavailable (private mode) — unlock still works
        // for this view, it just won't survive a tab switch.
      }
      onUnlock(apps)
    } catch {
      setError('Wrong passphrase, or the data is corrupt.')
      setBusy(false)
      setPass('')
    }
  }

  return (
    <div className="grid min-h-40 place-items-center rounded-[14px] border border-border bg-card p-8">
      <form onSubmit={submit} className="w-full max-w-sm space-y-3.5 text-center">
        <div className="flex items-center justify-center gap-2 text-sm font-semibold text-fg">
          <Lock size={15} />
          Applications are encrypted
        </div>
        <p className="text-[13px] text-mute">
          Enter your passphrase to decrypt them in your browser. Nothing is sent anywhere.
        </p>
        <input
          type="password"
          value={pass}
          onChange={(e) => setPass(e.target.value)}
          placeholder="Passphrase"
          autoFocus
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
    </div>
  )
}
