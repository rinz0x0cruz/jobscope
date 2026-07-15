import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { localServeToken, applicationUpdate } from '@/lib/outreach'
import type { Application } from '@/lib/schema'

/**
 * Drawer editor for an application's interview + offer details. Renders only
 * under local `jobscope serve` (it probes /api/token) — the public static site
 * has no backend, so it stays hidden. Writes through /api/application/update;
 * empty fields never clobber saved values, matching the store's upsert guard.
 */
export function OfferEditor({ app }: { app: Application }) {
  const [token, setToken] = useState<string | null>(null)
  const [interviewAt, setInterviewAt] = useState(app.interview_at || '')
  const [salary, setSalary] = useState(app.salary_offered || '')
  const [decision, setDecision] = useState(app.offer_accepted || '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let live = true
    localServeToken().then((t) => live && setToken(t))
    return () => {
      live = false
    }
  }, [])

  if (!token) return null

  const dirty =
    interviewAt !== (app.interview_at || '') ||
    salary !== (app.salary_offered || '') ||
    decision !== (app.offer_accepted || '')

  const save = async () => {
    setSaving(true)
    try {
      const res = await applicationUpdate(app.job_id, token, {
        interview_at: interviewAt,
        salary_offered: salary,
        offer_accepted: decision,
      })
      if (res.ok) toast.success('Offer details saved')
      else toast.error(res.error || 'Save failed')
    } catch {
      toast.error('Could not reach jobscope serve.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="border-t border-border px-5 py-4">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-mute">Offer &amp; interview</h3>
      <div className="space-y-2 text-[13px]">
        <label className="block">
          <span className="text-[11px] text-mute">Next interview</span>
          <input
            value={interviewAt}
            onChange={(e) => setInterviewAt(e.target.value)}
            placeholder="2026-07-20 14:00"
            className="mt-0.5 w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] text-fg outline-none focus:border-border-h"
          />
        </label>
        <label className="block">
          <span className="text-[11px] text-mute">Offer comp</span>
          <input
            value={salary}
            onChange={(e) => setSalary(e.target.value)}
            placeholder="₹28 LPA + 15% bonus"
            className="mt-0.5 w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] text-fg outline-none focus:border-border-h"
          />
        </label>
        <label className="block">
          <span className="text-[11px] text-mute">Decision</span>
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
            className="mt-0.5 w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-[13px] text-fg outline-none focus:border-border-h"
          >
            <option value="">—</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="declined">Declined</option>
          </select>
        </label>
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-bg2 px-3 py-1.5 text-[13px] font-medium text-fg transition hover:border-border-h disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save
        </button>
      </div>
    </section>
  )
}
