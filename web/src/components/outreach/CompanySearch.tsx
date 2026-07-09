import { useEffect, useState } from 'react'
import { Loader2, Search } from 'lucide-react'
import { companyOutreachPreview, localServeToken, type CompanyOutreach } from '@/lib/outreach'
import { CompanyCard } from './CompanyCard'

type Serve = 'loading' | 'on' | 'off'

/**
 * Company search: type a company (optionally its website) and get plausible HR
 * contacts + a résumé-attached draft. Live discovery fetches the employer's site,
 * so it runs only under local `jobscope serve`; on the published site it explains
 * how to run it (applied-company contacts will surface here without the backend).
 */
export function CompanySearch() {
  const [serve, setServe] = useState<Serve>('loading')
  const [token, setToken] = useState<string | null>(null)
  const [company, setCompany] = useState('')
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CompanyOutreach | null>(null)

  useEffect(() => {
    let live = true
    localServeToken().then((t) => {
      if (!live) return
      setToken(t)
      setServe(t ? 'on' : 'off')
    })
    return () => {
      live = false
    }
  }, [])

  const search = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token || !company.trim() || loading) return
    setLoading(true)
    setResult(null)
    try {
      const res = await companyOutreachPreview(company.trim(), token, { url: url.trim() || undefined })
      setResult(res)
    } catch {
      setResult({ ok: false, error: 'Could not reach jobscope serve.' })
    } finally {
      setLoading(false)
    }
  }

  if (serve === 'off') {
    return (
      <section className="rounded-[14px] border border-dashed border-border bg-card/60 p-5 text-[13px] text-mute">
        <div className="mb-1 text-sm font-semibold text-fg">Find HR contacts by company</div>
        Live HR-contact search fetches a company's site, so it runs when you launch{' '}
        <code className="rounded bg-bg2 px-1 py-0.5 text-dim">jobscope serve</code> locally — there it also sends
        with your résumé attached. Contacts for companies you've applied to will appear here on the published site.
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-4">
      <form onSubmit={search} className="rounded-[14px] border border-border bg-card p-5">
        <div className="mb-1 text-sm font-semibold">Find HR contacts by company</div>
        <p className="mb-3 text-[12px] text-mute">
          We fetch the company's own site for published recruiting addresses — never guessed from a name alone.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Company name — e.g. Acme Security"
            className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-[13px] text-fg outline-none focus:border-border-h"
          />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Website (optional)"
            className="rounded-lg border border-border bg-bg px-3 py-2 text-[13px] text-fg outline-none focus:border-border-h sm:w-56"
          />
          <button
            type="submit"
            disabled={serve === 'loading' || loading || !company.trim()}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} Find contacts
          </button>
        </div>
      </form>

      {loading && (
        <div className="flex items-center gap-2 px-1 text-[13px] text-mute">
          <Loader2 size={14} className="animate-spin" /> Searching {company}'s site for contacts…
        </div>
      )}

      {result && !result.ok && (
        <p className="px-1 text-[13px] text-stretch">
          {result.error}
          {result.needs_url && !url && ' — add the website above and search again.'}
        </p>
      )}

      {result && result.ok && <CompanyCard result={result} token={token as string} />}
    </section>
  )
}
