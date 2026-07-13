import { useEffect, useState } from 'react'
import { ExternalLink, Loader2, Mail, Radar, Save, Send } from 'lucide-react'
import { toast } from 'sonner'
import {
  companyOutreachPreview,
  companyOutreachSend,
  localServeToken,
  type CompanyOutreach,
} from '@/lib/outreach'
import { scoutCompany, type ScoutResponse } from '@/lib/scout'
import { TIER_COLOR } from '@/lib/schema'

/**
 * "Scout a company" — type a company name, fetch its public Greenhouse / Lever /
 * Ashby board, and rank its openings against your active profile. Renders only
 * under local `jobscope serve` (it probes /api/token) — the static site has no
 * backend to scrape with, so it stays hidden there. `Save` upserts the matches
 * into your pipeline (they appear in To-apply / Board on the next refresh).
 */
export function CompanyScout() {
  const [token, setToken] = useState<string | null>(null)
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [res, setRes] = useState<ScoutResponse | null>(null)
  const [reach, setReach] = useState<CompanyOutreach | null>(null)
  const [reaching, setReaching] = useState(false)
  const [sending, setSending] = useState(false)
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')

  useEffect(() => {
    let live = true
    localServeToken().then((t) => live && setToken(t))
    return () => {
      live = false
    }
  }, [])

  if (!token) return null

  const run = async (save = false) => {
    const name = company.trim()
    if (!name) return
    if (save) setSaving(true)
    else setLoading(true)
    try {
      const r = await scoutCompany(name, token, { save, limit: 30 })
      setRes(r)
      if (!save) setReach(null)
      if (!r.ok) toast.error(r.error || 'Scout failed')
      else if (save) toast.success(`Saved ${r.saved ?? 0} role${r.saved === 1 ? '' : 's'} to your pipeline`)
    } catch {
      toast.error('Could not reach jobscope serve.')
    } finally {
      if (save) setSaving(false)
      else setLoading(false)
    }
  }

  const reachOut = async () => {
    const name = res?.company
    if (!name) return
    setReaching(true)
    try {
      const r = await companyOutreachPreview(name, token)
      setReach(r)
      if (r.ok) {
        setTo(r.candidates?.[0]?.email ?? '')
        setSubject(r.subject ?? '')
        setBody(r.body ?? '')
      } else {
        toast.error(r.error || 'No contacts found')
      }
    } catch {
      toast.error('Could not reach jobscope serve.')
    } finally {
      setReaching(false)
    }
  }

  const sendMail = async () => {
    const name = res?.company
    if (!name || !to.trim()) return
    setSending(true)
    try {
      const r = await companyOutreachSend(name, token, { to, subject, body })
      if (r.ok && r.sent) {
        toast.success(`Emailed ${r.to}`)
        setReach(null)
      } else {
        toast.error(r.error || 'Send failed')
      }
    } catch {
      toast.error('Send failed')
    } finally {
      setSending(false)
    }
  }

  const mailtoHref = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
  const matches = (res?.results ?? []).filter((r) => r.tier !== 'Skip')

  return (
    <section className="mb-6 rounded-card border border-line bg-panel p-4">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Radar size={15} className="text-brand" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-ink">Scout a company</h3>
        <span className="text-[12px] text-ink-3">— pull its openings, ranked for your active profile</span>
      </div>

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void run(false)
        }}
      >
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Company (e.g. Rubrik, Databricks) — or Name|provider|slug"
          className="min-w-0 flex-1 rounded-lg border border-line bg-inset px-3 py-1.5 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-line-strong"
        />
        <button
          type="submit"
          disabled={loading || !company.trim()}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line bg-inset px-3 py-1.5 text-sm font-medium text-ink transition hover:border-line-strong disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Radar size={14} />} Scout
        </button>
      </form>

      {res && res.ok && (
        <div className="mt-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[12px] text-ink-3">
            <span>
              <span className="text-ink-2">{res.company}</span>{' '}
              <span className="text-ink-3">[{res.provider}/{res.slug}]</span> — {res.count} on board,{' '}
              <span className="text-ink-2">{res.matched} match</span> your profile
            </span>
            <div className="flex shrink-0 items-center gap-2">
              {matches.length > 0 && (
                <button
                  type="button"
                  onClick={() => void run(true)}
                  disabled={saving}
                  className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11px] font-medium text-brand transition hover:border-brand disabled:opacity-50"
                >
                  {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save {matches.length} to pipeline
                </button>
              )}
              <button
                type="button"
                onClick={() => void reachOut()}
                disabled={reaching}
                className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11px] font-medium text-ink-2 transition hover:border-line-strong hover:text-ink disabled:opacity-50"
              >
                {reaching ? <Loader2 size={12} className="animate-spin" /> : <Mail size={12} />} Reach out
              </button>
            </div>
          </div>

          {matches.length === 0 ? (
            <p className="text-[13px] text-ink-3">No openings matched your active profile.</p>
          ) : (
            <ul className="grid gap-2 md:grid-cols-2">
              {matches.map((r, i) => (
                <li
                  key={`${r.url}-${i}`}
                  className="flex items-start gap-2 rounded-lg border border-line bg-inset/40 px-3 py-2"
                >
                  <span
                    className="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums"
                    style={{
                      color: TIER_COLOR[r.tier],
                      background: `color-mix(in srgb, ${TIER_COLOR[r.tier]} 14%, transparent)`,
                    }}
                    title={r.rationale}
                  >
                    {Math.round(r.score)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium text-ink">{r.title}</span>
                    <span className="block truncate text-[12px] text-ink-3">{r.location || 'location n/a'}</span>
                  </span>
                  {r.url && (
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-0.5 shrink-0 text-ink-3 transition-colors hover:text-brand"
                      title="Open posting"
                    >
                      <ExternalLink size={14} aria-hidden="true" />
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}

          {reach && reach.ok && (
            <div className="mt-3 rounded-lg border border-line bg-inset/40 p-3">
              <div className="mb-2 flex items-center gap-2 text-[12px] text-ink-3">
                <Mail size={13} className="text-brand" aria-hidden="true" />
                <span>
                  Email HR at <span className="text-ink-2">{reach.company}</span>
                  {reach.domain ? <span className="text-ink-3"> · {reach.domain}</span> : null}
                </span>
              </div>
              {(reach.candidates?.length ?? 0) > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {reach.candidates!.map((c) => (
                    <button
                      key={c.email}
                      type="button"
                      onClick={() => setTo(c.email)}
                      title={`${c.confidence} confidence \u00b7 ${c.source}${c.note ? ' \u2014 ' + c.note : ''}`}
                      className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
                        c.email === to
                          ? 'border-brand bg-brand-weak text-brand'
                          : 'border-line text-ink-2 hover:border-line-strong'
                      }`}
                    >
                      {c.email}
                    </button>
                  ))}
                </div>
              )}
              <div className="space-y-2">
                <input
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  placeholder="recruiter@company.com"
                  className="w-full rounded-lg border border-line bg-panel px-2 py-1.5 text-[13px] text-ink outline-none focus:border-line-strong"
                />
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Subject"
                  className="w-full rounded-lg border border-line bg-panel px-2 py-1.5 text-[13px] text-ink outline-none focus:border-line-strong"
                />
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={5}
                  className="w-full resize-y rounded-lg border border-line bg-panel px-2 py-1.5 text-[13px] leading-relaxed text-ink outline-none focus:border-line-strong"
                />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <a
                  href={mailtoHref}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-[12px] font-medium text-ink transition hover:border-line-strong"
                >
                  <ExternalLink size={13} aria-hidden="true" /> Open in mail app
                </a>
                {reach.sendable && (
                  <button
                    type="button"
                    onClick={() => void sendMail()}
                    disabled={sending || !to.trim()}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-inset px-3 py-1.5 text-[12px] font-medium text-brand transition hover:border-brand disabled:opacity-50"
                  >
                    {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Send with résumé
                  </button>
                )}
                {reach.resume ? (
                  <span className="text-[11px] text-ink-3">attaches {reach.resume}</span>
                ) : null}
                {!reach.sendable ? (
                  <span className="text-[11px] text-ink-3">sending is off — use your mail app</span>
                ) : null}
              </div>
            </div>
          )}
          {reach && !reach.ok && (
            <p className="mt-2 text-[12px]" style={{ color: 'var(--stretch)' }}>
              {reach.error}
            </p>
          )}
        </div>
      )}

      {res && !res.ok && (
        <p className="mt-2 text-[12px]" style={{ color: 'var(--stretch)' }}>
          {res.error}
        </p>
      )}
    </section>
  )
}
