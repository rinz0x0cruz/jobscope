import { useEffect, useState } from 'react'
import { Copy, ExternalLink, Loader2, Mail, Send } from 'lucide-react'
import { toast } from 'sonner'
import { companyOutreachSend, type CompanyContact, type CompanyOutreach } from '@/lib/outreach'

const CONF: Record<string, string> = {
  high: 'text-strong',
  medium: 'text-good',
  low: 'text-mute',
}

function ContactRow({
  contact,
  selected,
  onPick,
}: {
  contact: CompanyContact
  selected: boolean
  onPick: () => void
}) {
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation()
    void navigator.clipboard?.writeText(contact.email).then(
      () => toast.success(`Copied ${contact.email}`),
      () => toast.error('Copy failed'),
    )
  }
  return (
    <button
      type="button"
      onClick={onPick}
      className={
        'flex w-full flex-col gap-0.5 rounded-[10px] border px-3 py-2 text-left transition ' +
        (selected ? 'border-accent bg-accent-dim' : 'border-border bg-bg2/60 hover:border-border-h')
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[13px] text-fg">{contact.email}</span>
        <span className="flex shrink-0 items-center gap-2">
          <span className={'text-[10px] font-semibold uppercase tracking-wide ' + (CONF[contact.confidence] || 'text-mute')}>
            {contact.confidence}
          </span>
          <span
            role="button"
            tabIndex={-1}
            onClick={copy}
            title="Copy address"
            className="rounded p-0.5 text-mute transition hover:text-fg"
          >
            <Copy size={13} />
          </span>
        </span>
      </div>
      <span className="text-[11px] text-mute">{contact.note}</span>
    </button>
  )
}

/**
 * The company card: plausible HR/recruiting contacts for a searched company plus an
 * editable, résumé-attached draft. "Open in mail app" (mailto) works everywhere;
 * "Send with résumé" appears when local sending is configured (apply.outreach.enabled
 * + email.*), and attaches your résumé server-side through the same guardrails as the CLI.
 */
export function CompanyCard({ result, token }: { result: CompanyOutreach; token: string }) {
  const candidates = result.candidates || []
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [sentTo, setSentTo] = useState('')

  useEffect(() => {
    setTo(candidates[0]?.email || '')
    setSubject(result.subject || '')
    setBody(result.body || '')
    setSentTo('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.company, result.domain])

  const mailtoHref = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`

  const send = async () => {
    setSending(true)
    try {
      const res = await companyOutreachSend(result.company || '', token, { to, subject, body })
      if (res.ok && res.sent) {
        toast.success(`Emailed ${res.to}`)
        setSentTo(res.to || to)
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
    <section className="rounded-[14px] border border-border bg-card p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{result.company}</h3>
        {result.domain && (
          <a
            href={`https://${result.domain}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[12px] text-signal hover:underline"
          >
            {result.domain} <ExternalLink size={11} />
          </a>
        )}
      </div>

      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-mute">
        Plausible HR contacts
      </div>
      <div className="flex flex-col gap-1.5">
        {candidates.length ? (
          candidates.map((c) => (
            <ContactRow key={c.email} contact={c} selected={c.email === to} onPick={() => setTo(c.email)} />
          ))
        ) : (
          <p className="text-[13px] text-mute">
            No public addresses found on their site — pick a role inbox or enter one below.
          </p>
        )}
      </div>

      <div className="mt-4 space-y-2 border-t border-border pt-4 text-[13px]">
        <label className="block">
          <span className="text-[11px] text-mute">To</span>
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="hr@company.com"
            className="mt-0.5 w-full rounded-lg border border-border bg-bg px-2 py-1.5 font-mono text-[13px] text-fg outline-none focus:border-border-h"
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
          <span className="text-[11px] text-mute">Body{result.resume ? ` · attaches ${result.resume}` : ''}</span>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            className="mt-0.5 w-full resize-y rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] leading-relaxed text-fg outline-none focus:border-border-h"
          />
        </label>

        {sentTo && <p className="text-[12px] text-strong">Sent to {sentTo}.</p>}
        {!result.sendable && (
          <p className="text-[12px] text-mute">
            <span className="text-fg">Open in mail app</span> composes in your own client — attach{' '}
            {result.resume ? <code>{result.resume}</code> : 'your résumé'} and send. To send with the résumé
            attached automatically, set <code>apply.outreach.enabled</code> + <code>email.*</code>.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <a
            href={mailtoHref}
            className={
              'inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-bg2 px-3 py-2 text-[13px] font-medium text-fg transition hover:border-border-h ' +
              (to ? '' : 'pointer-events-none opacity-50')
            }
          >
            <Mail size={14} /> Open in mail app
          </a>
          {result.sendable && (
            <button
              type="button"
              disabled={sending || !to}
              onClick={send}
              className="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-3.5 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Send with résumé
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
