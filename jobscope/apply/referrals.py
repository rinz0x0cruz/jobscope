"""Referral surfacing: where in your pipeline you already have a way in.

Reads the legit-only referral leads that ``enrich`` discovered (LinkedIn/Google
search links + public GitHub profiles, each with a deterministic outreach draft)
and surfaces them per company -- a "network activation" digest across your top
matches and applications, plus the copy-ready outreach draft at the moment of
applying.

Deterministic + offline: it reads stored contacts. ``--discover`` fetches fresh
leads for one job's company on demand (network).
"""
from __future__ import annotations

import textwrap


def _status_map(store) -> dict[str, str]:
    return {a["job_id"]: a.get("status", "") for a in store.applications()}


def paths_for(store, company: str) -> dict:
    """Split a company's stored leads into real profiles vs search links + a draft."""
    leads = store.contacts_for(company) if company else []
    real = [c for c in leads if c.get("source") == "github"]
    searches = [c for c in leads if c.get("source") != "github"]
    draft = next((c.get("outreach") for c in real if c.get("outreach")), "")
    return {"company": company, "leads": leads, "real": real,
            "searches": searches, "draft": draft}


def discover_leads(cfg, store, job) -> dict:
    """Fetch + store fresh referral leads for a job's company, then return paths."""
    from jobscope.enrich import contacts as _contacts
    if job.company:
        found = _contacts.find(job.company, job)
        if found:
            store.save_contacts(found)
    return paths_for(store, job.company)


def pipeline_referrals(store, *, top: int = 25) -> list[dict]:
    """Every company you have referral leads for, best live match first.

    Referral relationships outlast a single posting, so a company whose role has
    since closed still appears (marked) below those with a live opening.
    """
    status = _status_map(store)
    best: dict[str, object] = {}          # highest-scored open job per company
    for job in store.jobs(order_by_score=True):
        c = (job.company or "").strip().lower()
        if c and c not in best:
            best[c] = job
    out: list[dict] = []
    for company in store.companies_with_contacts():
        p = paths_for(store, company)
        if not p["leads"]:
            continue
        job = best.get(company.strip().lower())
        p.update(job_id=getattr(job, "id", ""), title=getattr(job, "title", ""),
                 tier=getattr(job, "tier", ""), open=bool(job),
                 status=status.get(getattr(job, "id", ""), "") if job else "")
        out.append(p)
    out.sort(key=lambda p: (not p["open"], -len(p["real"]), -len(p["leads"])))
    return out[:top]


# --- rendering -------------------------------------------------------------
def _url(c: dict) -> str:
    return c.get("profile_url") or c.get("search_url") or ""


def render_digest(items: list[dict]) -> str:
    if not items:
        return ("  no referral paths yet -- run `enrich` to discover leads "
                "(search links + public profiles) for your matched companies")
    out = ["  referral paths (where you already have a way in -- leads outlast a posting):"]
    named = live = 0
    for p in items:
        if p["real"]:
            named += 1
        parts = []
        if p["real"]:
            parts.append(f"{len(p['real'])} profile{'s' if len(p['real']) != 1 else ''}")
        if p["searches"]:
            parts.append(f"{len(p['searches'])} search link{'s' if len(p['searches']) != 1 else ''}")
        if p.get("open"):
            live += 1
            tag = f"[{p['status']}]" if p["status"] else (f"[{p['tier']}]" if p["tier"] else "[open]")
            ctx = p["title"][:38]
        else:
            tag = "[closed]"
            ctx = "(no open role -- network anyway)"
        out.append(f"    {p['company'][:24]:24} {', '.join(parts):22} {tag:12} {ctx}")
    out.append(f"  {len(items)} compan{'ies' if len(items) != 1 else 'y'} with referral paths "
               f"-- {named} with a named profile, {live} with a live role.")
    out.append("  tip: `jobscope referrals --job <id>` shows the copy-ready outreach draft.")
    return "\n".join(out)


def render_one(job, p: dict) -> str:
    out = [f"  referral paths for {p['company'] or '?'} -- {job.title}:"]
    if not p["leads"]:
        out.append("    none stored. Run `jobscope referrals --job <id> --discover` "
                   "or `enrich --job <id>` to find leads.")
        return "\n".join(out)
    if p["real"]:
        out.append("    real profiles:")
        for c in p["real"]:
            title = f" -- {c['title']}" if c.get("title") else ""
            out.append(f"      - {c.get('name', 'lead')}{title}  [{c.get('source')}]  {_url(c)}")
    if p["searches"]:
        out.append("    search links:")
        for c in p["searches"]:
            out.append(f"      - {c.get('name', 'lead')} -> {_url(c)}")
    if p["draft"]:
        out.append("    outreach draft (copy-ready):")
        for line in textwrap.wrap(p["draft"], width=76):
            out.append(f"      {line}")
    else:
        out.append("    (no named profile yet -- use the search links to find someone, "
                   "then `jobscope outreach <id>` drafts a message)")
    return "\n".join(out)


def run(cfg: dict, store, *, job_id: str | None = None,
        discover: bool = False, top: int = 25) -> int:
    if job_id:
        job = store.get_job(job_id)
        if job is None:
            print(f"  job not found: {job_id}")
            return 1
        p = discover_leads(cfg, store, job) if discover else paths_for(store, job.company)
        print(render_one(job, p))
        return 0
    print(render_digest(pipeline_referrals(store, top=top)))
    return 0
