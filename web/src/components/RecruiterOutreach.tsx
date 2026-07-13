import { useEffect, useState } from 'react'
import { Loader2, Mail, Send } from 'lucide-react'
import { toast } from 'sonner'
import { localServeToken, outreachPreview, outreachSend, type OutreachPreview } from '@/lib/outreach'

/**
 * Drawer panel to email a recruiter. Only renders under local `jobscope serve`
 * (it probes /api/token) — on the public site there's no backend, so it stays
 * hidden. Resolves a contact, lets you review/edit the tailored email, and sends
 * it with your résumé through the same guardrails as the CLI.
 */
export function RecruiterOutreach({ jobId, followup = false }: { jobId: string; followup?: boolean }) {
  const [token, setToken] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<OutreachPreview | null>(null)
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    let live = true
    localServeToken().then((t) => live && setToken(t))
    return () => {
      live = false
    }
  }, [])

  // reset when the drawer switches to a different job
  useEffect(() => {
    setOpen(false)
    setPreview(null)
  }, [jobId])

  if (!token) return null

  const draftFor = async (addr?: string) => {
    setLoading(true)
    try {
      const p = await outreachPreview(jobId, token, addr, followup)
      setPreview(p)
      if (p.ok) {
        setTo(p.to || addr || '')
        setSubject(p.subject || '')
        setBody(p.body || '')
      }
    } catch {
      setPreview({ ok: false, error: 'Could not reach jobscope serve.' })
    } finally {
      setLoading(false)
    }
  }

  const start = () => {
    setOpen(true)
    void draftFor()
  }

  const send = async () => {
    setSending(true)
    try {
      const res = await outreachSend(jobId, token, { to, subject, body })
      if (res.ok && res.sent) {
        toast.success(`Emailed ${res.to}`)
        setOpen(false)
      } else {
        toast.error(res.error || 'Send failed')
      }
    } catch {
      toast.error('Send failed')
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="border-t border-border px-5 py-4">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-mute">{followup ? 'Follow up' : 'Email recruiter'}</h3>

      {!open ? (
        <button
          type="button"
          onClick={start}
          className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-bg2 px-3 py-1.5 text-[13px] font-medium text-fg transition hover:border-border-h"
        >
          <Mail size={14} /> {followup ? 'Draft follow-up' : 'Find contact & draft email'}
        </button>
      ) : loading ? (
        <div className="flex items-center gap-2 text-[13px] text-mute">
          <Loader2 size={14} className="animate-spin" /> Resolving contact + drafting…
        </div>
      ) : preview && !preview.ok ? (
        <div className="text-[13px]">
          <p className="text-stretch">{preview.error}</p>
          {preview.needs_address && (
            <input
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="recruiter@company.com"
              className="mt-2 w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] text-fg outline-none focus:border-border-h"
            />
          )}
          <div className="mt-2 flex gap-3">
            {preview.needs_address && to && (
              <button type="button" onClick={() => void draftFor(to)} className="text-[12px] font-medium text-accent hover:underline">
                Draft for this address
              </button>
            )}
            <button type="button" onClick={() => setOpen(false)} className="text-[12px] text-dim hover:text-fg">
              Close
            </button>
          </div>
        </div>
      ) : preview ? (
        <div className="space-y-2 text-[13px]">
          <div className="text-[11px] text-mute">
            {preview.source} · {preview.confidence} confidence — {preview.note}
          </div>
          <label className="block">
            <span className="text-[11px] text-mute">To</span>
            <input
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="mt-0.5 w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] text-fg outline-none focus:border-border-h"
            />
          </label>
          <label className="block">
            <span className="text-[11px] text-mute">Subject</span>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="mt-0.5 w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] text-fg outline-none focus:border-border-h"
            />
          </label>
          <label className="block">
            <span className="text-[11px] text-mute">Body{preview.resume ? ` · attaches ${preview.resume}` : ''}</span>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={7}
              className="mt-0.5 w-full resize-y rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] leading-relaxed text-fg outline-none focus:border-border-h"
            />
          </label>
          {preview.already_at && (
            <p className="text-[12px] text-stretch">Already contacted on {preview.already_at.slice(0, 10)}.</p>
          )}
          {!preview.sendable && (
            <p className="text-[12px] text-mute">
              Sending is off — set <code>apply.outreach.enabled</code> + <code>email.*</code> to enable Send.
            </p>
          )}
          <div className="flex items-center gap-3 pt-1">
            <button
              type="button"
              disabled={sending || !preview.sendable || !to}
              onClick={send}
              className="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-3.5 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Send
            </button>
            <button type="button" onClick={() => setOpen(false)} className="text-[13px] text-dim hover:text-fg">
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
