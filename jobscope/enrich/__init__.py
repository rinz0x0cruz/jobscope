"""Enrichment orchestrator.

For the top-ranked jobs (or a single job), gather public intel per company and
persist it. Every source is best-effort and independent; a failure in one is
logged and skipped. Deterministic by default -- AI summaries are layered on in
Phase 3 via `tailor`/`ai`.

The per-source `if cfg[...]: sections[...] = X.enrich(...)` ladder is gone: each
*section* source self-registers via the `@source(...)` decorator (see
`registry.py`), so adding an intel source is one new module + a decorator, not an
edit here -- `run()` just iterates `SECTION_SOURCES`. `contacts` (returns leads
-> `save_contacts`) and `brief` (AI synthesis over the gathered sections ->
``save_job_analysis(brief=...)``) have distinct storage semantics and stay wired
explicitly below. Posted compensation and briefs are versioned by job and selected
resume; stock, news, sentiment, and lookup links remain company-scoped.
"""
from __future__ import annotations

from typing import Optional

from .registry import SECTION_SOURCES, EnrichContext
# Importing the source modules runs their `@source(...)` decorators, which
# self-register into SECTION_SOURCES (registration order = the order listed here:
# comp, stock, reddit, news, glassdoor -- matching the old hardcoded ladder).
from . import comp, stock, reddit, news, glassdoor  # noqa: F401 - import = register
from . import brief, contacts

ANALYSIS_VERSION = 1
_COMPANY_COMP_KEYS = frozenset({"levels_fyi", "levels_search"})


def for_job(store, job) -> dict:
    """Compose company intelligence with analysis for one job/resume/version."""
    company_data = store.get_enrichment(job.company) if job.company else {}
    out = {k: v for k, v in (company_data or {}).items()
           if k not in {"brief", "updated"}}

    company_comp = {
        key: value
        for key, value in ((company_data or {}).get("comp") or {}).items()
        if key in _COMPANY_COMP_KEYS
    }
    analysis = store.get_job_analysis(
        job.id, resume_base=job.resume_base or "", version=ANALYSIS_VERSION)
    posting_comp = comp.posting(job) or analysis.get("comp") or {}
    merged_comp = {**company_comp, **posting_comp}
    if merged_comp:
        out["comp"] = merged_comp
    if analysis.get("brief"):
        out["brief"] = analysis["brief"]
    return out


def run(cfg: dict, store, job_id: Optional[str] = None) -> int:
    ecfg = cfg["enrich"]
    jobs = _select_jobs(store, ecfg, job_id)
    if not jobs:
        print("  no jobs to enrich. Run `scan` + `match` first.")
        return 1

    # one representative job per company (prefer the highest-scored)
    by_company: dict[str, object] = {}
    for j in jobs:
        if j.company and j.company not in by_company:
            by_company[j.company] = j

    print(f"  enriching {len(by_company)} companies / {len(jobs)} role(s)...")
    for company, job in by_company.items():
        sections = {}
        try:
            ctx = EnrichContext(company=company, job=job, ecfg=ecfg)
            for src in SECTION_SOURCES:
                if ecfg.get(src.config_key):
                    sections[src.section] = src.call(src.fn, ctx)
            store.save_enrichment(company, **{k: v for k, v in sections.items() if v})
            if ecfg.get("contacts"):
                leads = contacts.find(company, job)
                store.save_contacts(leads)
            print(f"    {company}: " + _summary(sections))
        except Exception as e:  # noqa: BLE001 - keep enriching others
            print(f"    {company}: error ({e})")
            store.log_run(f"enrich:{company}", 0, "error")
    for job in jobs:
        if not job.company:
            continue
        try:
            role_data = for_job(store, job)
            role_comp = comp.posting(job)
            role_brief = (brief.build(cfg, store, job.company, job, role_data)
                          if ecfg.get("brief") else None)
            store.save_job_analysis(
                job.id, resume_base=job.resume_base or "", version=ANALYSIS_VERSION,
                comp=role_comp, brief=role_brief,
            )
        except Exception as exc:  # noqa: BLE001 - one role must not block the rest
            print(f"    {job.company} / {job.title}: analysis error ({exc})")
            store.log_run(f"analyze:{job.id}", 0, "error")
    store.log_run("enrich", len(by_company), "ok")
    return 0


def _select_jobs(store, ecfg: dict, job_id: Optional[str]):
    if job_id:
        job = store.get_job(job_id)
        return [job] if job else []
    ranked = store.jobs(order_by_score=True)
    worth = [j for j in ranked if j.tier != "Skip"]
    pool = worth or ranked
    return pool[: ecfg.get("top_n", 10)]


def _summary(sections: dict) -> str:
    bits = []
    st = sections.get("stock")
    if st and st.get("ticker"):
        bits.append(f"{st['ticker']} {st.get('price', '?')}")
    elif st and st.get("public") is False:
        bits.append("private")
    cm = sections.get("comp")
    if cm and cm.get("range"):
        bits.append(cm["range"])
    nw = sections.get("news")
    if nw:
        bits.append(f"{len(nw)} news")
    rd = sections.get("reddit")
    if rd and rd.get("count"):
        bits.append(f"reddit×{rd['count']} ({rd.get('sentiment', '?')})")
    return ", ".join(bits) or "no public data"
