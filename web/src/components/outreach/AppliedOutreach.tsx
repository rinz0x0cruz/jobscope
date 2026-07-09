import { Copy, ExternalLink, Mail } from 'lucide-react'
import { toast } from 'sonner'
import type { AppliedCompany, CompanyContact, Profile } from '@/lib/schema'
import { mailtoHref } from '@/lib/draft'

const CONF: Record<string, string> = { high: 'text-strong', medium: 'text-good', low: 'text-mute' }

function copy(email: string) {
  void navigator.clipboard?.writeText(email).then(
    () => toast.success(`Copied ${email}`),
    () => toast.error('Copy failed'),
  )
}

function Contact({ contact, company, profile }: { contact: CompanyContact; company: string; profile: Profile | null }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-[10px] border border-border bg-bg2/60 px-3 py-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-mono text-[13px] text-fg">{contact.email}</span>
          <span className={'text-[10px] font-semibold uppercase tracking-wide ' + (CONF[contact.confidence] || 'text-mute')}>
            {contact.confidence}
          </span>
        </div>
        <div className="text-[11px] text-mute">{contact.note}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={() => copy(contact.email)}
          title="Copy address"
          className="rounded-md border border-border bg-bg2 p-1.5 text-mute transition hover:text-fg"
        >
          <Copy size={13} />
        </button>
        <a
          href={mailtoHref(contact.email, company, profile)}
          title="Compose in your mail app"
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg2 px-2.5 py-1.5 text-[12px] font-medium text-fg transition hover:border-border-h"
        >
          <Mail size={13} /> Compose
        </a>
      </div>
    </div>
  )
}

function CompanyBlock({ item, profile }: { item: AppliedCompany; profile: Profile | null }) {
  return (
    <section className="rounded-[14px] border border-border bg-card p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold">{item.company}</h4>
          {item.status && (
            <span className="rounded-full border border-border bg-bg2 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-dim">
              {item.status}
            </span>
          )}
        </div>
        {item.domain && (
          <a
            href={`https://${item.domain}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[12px] text-signal hover:underline"
          >
            {item.domain} <ExternalLink size={11} />
          </a>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        {item.contacts.map((c) => (
          <Contact key={c.email} contact={c} company={item.company} profile={profile} />
        ))}
      </div>
      <p className="mt-2.5 text-[11px] text-mute">
        Compose opens your mail app with a short intro pre-filled — attach your résumé and send.
      </p>
    </section>
  )
}

/**
 * HR contacts for the companies you're actively applied to, pre-computed during
 * the refresh (deterministic on-site discovery + inbox recruiters + optional
 * finder) and baked into the payload behind the unlock — so they're available on
 * the published site with a one-click mailto compose.
 */
export function AppliedOutreach({ applied, profile }: { applied: AppliedCompany[]; profile: Profile | null }) {
  if (!applied.length) {
    return (
      <section className="rounded-[14px] border border-dashed border-border bg-card/60 p-5 text-[13px] text-mute">
        <div className="mb-1 text-sm font-semibold text-fg">HR contacts at companies you've applied to</div>
        These appear here after a refresh discovers them (or run{' '}
        <code className="rounded bg-bg2 px-1 py-0.5 text-dim">jobscope outreach-scan</code> locally). Active
        applications only — rejected/closed roles are skipped.
      </section>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold">HR contacts at companies you've applied to</h3>
        <p className="mt-0.5 text-[12px] text-mute">
          {applied.length} active {applied.length === 1 ? 'company' : 'companies'} with discovered contacts —
          reach a human directly.
        </p>
      </div>
      {applied.map((item) => (
        <CompanyBlock key={item.company} item={item} profile={profile} />
      ))}
    </div>
  )
}
