// @vitest-environment node
import { describe, it, expect } from 'vitest'
import { webcrypto } from 'node:crypto'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import type { EncBlob } from '@/lib/schema'
import { isEncPointer, unlockDashboard } from '@/lib/unlock'

// Build an EncBlob exactly like scripts/build-secure-apps.mjs (AES-256-GCM over
// JSON, PBKDF2-SHA256 key, ciphertext+tag base64 in WebCrypto layout).
async function makeBlob(obj: unknown, passphrase: string): Promise<EncBlob> {
  const enc = new TextEncoder()
  const salt = webcrypto.getRandomValues(new Uint8Array(16))
  const iv = webcrypto.getRandomValues(new Uint8Array(12))
  const iter = 210000
  const baseKey = await webcrypto.subtle.importKey('raw', enc.encode(passphrase), 'PBKDF2', false, ['deriveKey'])
  const key = await webcrypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: iter, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt'],
  )
  const ct = new Uint8Array(await webcrypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(JSON.stringify(obj))))
  const b64 = (u: Uint8Array) => Buffer.from(u).toString('base64')
  return { v: 1, kdf: 'PBKDF2-SHA256', iter, salt: b64(salt), iv: b64(iv), ct: b64(ct) }
}

// Feature: whole-site passphrase unlock (lib/unlock).
describe('unlockDashboard', () => {
  const FULL = {
    generated: '2026-07-07',
    total: 1,
    rows: [{ id: 'j1', title: 'Security Engineer', description: 'Confidential JD text', rationale: 'strong fit' }],
    overview: { funnel: { applied: 2, interview: 1 }, gaps: [], considered: 0, targets: [] },
    applications: [{ job_id: 'j1', company: 'Acme', title: 'Security Engineer', status: 'applied', applied_at: '', updated: '', source: '', interview_at: '', salary_offered: '', offer_accepted: '', timeline: [] }],
  }

  it('decrypts an inline blob back to the full un-redacted dashboard', async () => {
    const blob = await makeBlob(FULL, 'correct horse battery staple')
    const out = await unlockDashboard(blob, 'correct horse battery staple')
    expect(out.rows[0].description).toBe('Confidential JD text')
    expect(out.rows[0].rationale).toBe('strong fit')
    expect(out.applications).toHaveLength(1)
    expect(out.overview.funnel.applied).toBe(2)
    expect(out.companies).toEqual([])
    expect(out.reviews).toEqual([expect.objectContaining({
      job_id: 'j1', state: 'saved', origins: ['legacy'],
    })])
    expect(out.activity_audit).toEqual({
      recent_runs: [], selected_run_id: '', decisions: [], recoverable_applications: [],
    })
  })

  it('migrates explicit empty reviews on a nonempty legacy payload', async () => {
    const blob = await makeBlob({ ...FULL, companies: [], reviews: [] }, 'legacy-empty')
    const out = await unlockDashboard(blob, 'legacy-empty')

    expect(out.reviews).toEqual([expect.objectContaining({
      job_id: 'j1', state: 'saved', origins: ['legacy'],
    })])
  })

  it('throws on a wrong passphrase (GCM tag mismatch)', async () => {
    const blob = await makeBlob(FULL, 'right-passphrase')
    await expect(unlockDashboard(blob, 'wrong-passphrase')).rejects.toBeTruthy()
  })

  it('decrypts an envelope produced by build-secure-apps.mjs', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'jobscope-unlock-'))
    try {
      const dashboardPath = join(dir, 'dashboard.json')
      const encryptedPath = join(dir, 'site.enc.json')
      writeFileSync(dashboardPath, JSON.stringify(FULL))
      const script = fileURLToPath(new URL('../../scripts/build-secure-apps.mjs', import.meta.url))
      const template = fileURLToPath(new URL('../../scripts/apps-template.html', import.meta.url))
      const result = spawnSync(
        process.execPath,
        [script, dashboardPath, template, '-', encryptedPath],
        { input: 'node-to-browser-passphrase', encoding: 'utf8' },
      )
      expect(result.status, result.stderr).toBe(0)
      const blob = JSON.parse(readFileSync(encryptedPath, 'utf8')) as EncBlob

      const out = await unlockDashboard(blob, 'node-to-browser-passphrase')

      expect(out.rows[0].description).toBe('Confidential JD text')
      expect(out.applications).toHaveLength(1)
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('rejects unsupported envelope metadata before key derivation', async () => {
    const blob = await makeBlob(FULL, 'right-passphrase')
    await expect(unlockDashboard({ ...blob, v: 2 }, 'right-passphrase')).rejects.toThrow(
      'unsupported encrypted payload version',
    )
    await expect(
      unlockDashboard({ ...blob, kdf: 'PBKDF2-SHA1' }, 'right-passphrase'),
    ).rejects.toThrow('unsupported encrypted payload KDF')
  })

  it('detects a lazy pointer vs an inline blob', () => {
    expect(isEncPointer({ v: 1, url: 'site.enc.json' })).toBe(true)
    expect(isEncPointer({ v: 2, url: 'site.enc.json' })).toBe(false)
    expect(isEncPointer({ v: 1, kdf: 'PBKDF2-SHA256', iter: 1, salt: 'a', iv: 'b', ct: 'c' })).toBe(false)
  })
})
