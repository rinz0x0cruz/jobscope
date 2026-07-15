"""Interview-prep hub: everything to walk in prepared, assembled per job.

Pulls together what jobscope already knows -- your fit (strengths to lead with +
gaps to prepare), likely interview topics drawn from the JD, a STAR story-bank
scaffold, the blunt company brief, a referral path (a warm intro), and your own
notes -- and lets you jot a date-stamped note (`--note`).

Deterministic + offline: it reads stored data (the company brief and any AI stay
behind their existing optional paths). Nothing here needs a network or a model.
"""
from __future__ import annotations

import textwrap

from jobscope.analyze import coverage
from jobscope.apply import referrals
from jobscope import enrich as enrichment


def prep_sheet(cfg: dict, store, job, resume) -> dict:
    """Assemble the per-job interview-prep sheet from stored + derived data."""
    from jobscope.apply import tailor
    analysis = tailor.analyze(resume, job)

    reqs = coverage.extract_requirements(job)
    topics = [r["text"] for r in reqs if r["kind"] == "responsibility"]
    if len(topics) < 3:                       # thin JD -> fall back to any requirement
        topics = [r["text"] for r in reqs]

    strengths = analysis["matched"][:6]
    enr = enrichment.for_job(store, job)
    brief = (enr or {}).get("brief") or {}
    app = store.get_application(job.id) or {}
    return {
        "company": job.company,
        "title": job.title,
        "score": job.score,
        "tier": job.tier,
        "coverage": analysis["coverage"],
        "strengths": strengths,
        "gaps": analysis["missing"][:6],
        "topics": topics[:6],
        "star": (strengths[:4] or [job.title]),
        "brief": brief.get("text", ""),
        "referrals": referrals.paths_for(store, job.company),
        "notes": (app.get("notes") or "").strip(),
    }


def render_sheet(job, s: dict) -> str:
    out = [f"  Interview prep -- {s['title']} @ {s['company'] or '?'}"]
    fit = f"fit {s['score']:.0f}/100 [{s['tier']}]" if s["score"] else f"[{s['tier'] or 'unscored'}]"
    out.append(f"  {fit}  |  JD keyword coverage {s['coverage']:g}%")

    out.append("  lead with your strengths:")
    out.append(f"    {', '.join(s['strengths']) or '(no matched skills -- import a resume)'}")
    if s["gaps"]:
        out.append("  be ready to address gaps:")
        out.append(f"    {', '.join(s['gaps'])}")

    if s["topics"]:
        out.append("  likely topics (from the JD):")
        for t in s["topics"]:
            out.append(f"    - {t if len(t) <= 92 else t[:89] + '...'}")

    if s["star"]:
        out.append("  STAR stories to prepare (Situation / Task / Action / Result):")
        for theme in s["star"]:
            out.append(f"    - a time you applied {theme}: the situation, your task, "
                       f"the action you took, and the measurable result")

    if s["brief"]:
        out.append("  company brief:")
        for line in textwrap.wrap(s["brief"], 92)[:6]:
            out.append(f"    {line}")
    else:
        out.append("  company brief: (none stored -- run `jobscope brief <id>`)")

    paths = s["referrals"]
    if paths["leads"]:
        out.append(f"  referral path: {len(paths['real'])} profile(s), "
                   f"{len(paths['searches'])} search link(s) -- `jobscope referrals --job {job.id}`")
    else:
        out.append(f"  referral path: none stored -- `jobscope referrals --job {job.id} --discover`")

    if s["notes"]:
        out.append("  your notes:")
        for line in s["notes"].splitlines():
            out.append(f"    {line}")
    else:
        out.append(f'  your notes: (none -- add with `jobscope interview {job.id} --note "..."`)')
    return "\n".join(out)


def run(cfg: dict, store, job_id: str, *, note: str | None = None,
        resume_name: str | None = None) -> int:
    job = store.get_job(job_id)
    if job is None:
        print(f"  job not found: {job_id}")
        return 1
    if note:
        store.append_note(job.id, note)
        print(f"  noted for {job.title} @ {job.company or '?'}")

    resume = store.get_resume(resume_name) if resume_name else (
        store.get_named_resume(job.resume_base) if job.resume_base else store.get_resume())
    if resume is None:
        if note:
            return 0                          # the note was saved; nothing to render
        print("  no resume found. Run `resume import <path>` first.")
        return 1
    print(render_sheet(job, prep_sheet(cfg, store, job, resume)))
    return 0
