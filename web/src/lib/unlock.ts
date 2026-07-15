import type { DashboardData, EncBlob, EncRef } from './schema'

// sessionStorage key: an unlock survives tab switches / reloads within the same
// tab, but is cleared when the tab closes (never persisted to disk).
export const UNLOCK_KEY = 'jobscope:site'

/** The baked marker is a lazy pointer (published build) rather than an inline blob. */
export function isEncPointer(ref: EncRef): ref is { v: number; url: string } {
  return ref.v === 1 && typeof (ref as { url?: unknown }).url === 'string'
}

function validateBlob(value: unknown): EncBlob {
  if (!value || typeof value !== 'object') throw new Error('invalid encrypted payload')
  const blob = value as Partial<EncBlob>
  if (blob.v !== 1) throw new Error(`unsupported encrypted payload version: ${String(blob.v)}`)
  if (blob.kdf !== 'PBKDF2-SHA256') throw new Error(`unsupported encrypted payload KDF: ${String(blob.kdf)}`)
  if (!Number.isInteger(blob.iter) || (blob.iter ?? 0) < 210_000) {
    throw new Error('invalid encrypted payload iteration count')
  }
  for (const field of ['salt', 'iv', 'ct'] as const) {
    if (typeof blob[field] !== 'string' || !blob[field]) {
      throw new Error(`invalid encrypted payload field: ${field}`)
    }
  }
  return blob as EncBlob
}

function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

/** Resolve the ciphertext: fetch it if the baked marker is a lazy pointer. */
async function resolveBlob(ref: EncRef): Promise<EncBlob> {
  if (!isEncPointer(ref)) return validateBlob(ref)
  const url = new URL(ref.url, document.baseURI).href
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) throw new Error(`encrypted payload fetch failed (${res.status})`)
  return validateBlob(await res.json())
}

/**
 * Fetch (if the baked marker is a lazy pointer) and AES-256-GCM decrypt the full
 * un-redacted dashboard in-browser. PBKDF2-SHA256 derives the 256-bit key from
 * the passphrase; a wrong passphrase throws (GCM tag mismatch). Mirrors
 * scripts/build-secure-apps.mjs. Nothing is ever sent anywhere.
 */
export async function unlockDashboard(ref: EncRef, passphrase: string): Promise<DashboardData> {
  const blob = await resolveBlob(ref)
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
  return JSON.parse(new TextDecoder().decode(pt)) as DashboardData
}

/** Read a previously-unlocked payload cached for this tab (or null). */
export function readCachedUnlock(): DashboardData | null {
  try {
    const s = sessionStorage.getItem(UNLOCK_KEY)
    return s ? (JSON.parse(s) as DashboardData) : null
  } catch {
    return null
  }
}

export function cacheUnlock(data: DashboardData): void {
  try {
    sessionStorage.setItem(UNLOCK_KEY, JSON.stringify(data))
  } catch {
    // sessionStorage may be unavailable (private mode) or over quota — unlock
    // still works for this view, it just won't survive a reload.
  }
}

export function clearUnlock(): void {
  try {
    sessionStorage.removeItem(UNLOCK_KEY)
  } catch {
    /* ignore */
  }
}
