"""Enrichment orchestrator.

For the top-ranked jobs (or a single job), gather public intel per company and
persist it. Every source is best-effort and independent; a failure in one is
logged and skipped. Deterministic by default -- AI summaries are layered on in
Phase 3 via `tailor`/`ai`.
"""
from __future__ import annotations

from typing import Optional

from . import brief, comp, contacts, glassdoor, news, reddit, stock


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

    print(f"  enriching {len(by_company)} companies...")
    for company, job in by_company.items():
        sections = {}
        try:
            if ecfg.get("compensation"):
                sections["comp"] = comp.enrich(company, job)
            if ecfg.get("stock"):
                sections["stock"] = stock.enrich(company)
            if ecfg.get("reddit"):
                sections["reddit"] = reddit.enrich(company)
            if ecfg.get("news"):
                sections["news"] = news.enrich(company, ecfg.get("news_feeds", []))
            if ecfg.get("glassdoor"):
                sections["glassdoor"] = glassdoor.enrich(company)
            store.save_enrichment(company, **{k: v for k, v in sections.items() if v})
            if ecfg.get("contacts"):
                leads = contacts.find(company, job)
                store.save_contacts(leads)
            if ecfg.get("brief"):
                b = brief.build(cfg, store, company, job, sections)
                store.save_enrichment(company, brief=b)
            print(f"    {company}: " + _summary(sections))
        except Exception as e:  # noqa: BLE001 - keep enriching others
            print(f"    {company}: error ({e})")
            store.log_run(f"enrich:{company}", 0, "error")
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
