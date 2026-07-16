"""On-demand company scout: fetch a company's public ATS board (Greenhouse / Lever /
Ashby) and score its openings against the *active* search profile's résumé.

Unlike the batch ``scan`` (config-listed companies), this resolves a company by
name at call time -- known slug, an explicit ``provider|slug`` override, or a
best-effort probe. It needs the network, so it runs under local ``jobscope serve``
or the CLI, never on the static site. Deterministic scoring only (AI off).
"""
from __future__ import annotations

from typing import Any, Optional

from jobscope.analyze.review import persist_scored_job, score_jobs
from jobscope.ingest import ats


def scout(cfg: dict, store, company: str, *, provider: Optional[str] = None,
          slug: Optional[str] = None, save: bool = False, limit: int = 40) -> dict[str, Any]:
    """Fetch ``company``'s board and rank its openings against the active profile.

    Returns ``{ok, company, provider, slug, count, matched, saved, results[]}`` or
    ``{ok: False, error, needs_slug?}``. ``save`` upserts the non-Skip hits into the
    store so they flow into the To-apply list / Board on the next refresh.
    """
    company = (company or "").strip()
    if not company:
        return {"ok": False, "error": "enter a company name"}

    resolved = ats.resolve_board(company, provider=provider, slug=slug)
    if resolved is None:
        return {"ok": False, "needs_slug": True,
                "error": (f"no public Greenhouse/Lever/Ashby board found for '{company}'. "
                          f"Try an explicit board, e.g. \"{company}|lever|<slug>\".")}
    name, prov, board_slug = resolved

    fetch = ats.fetch_company_result(name, prov, board_slug)
    if not fetch.successful:
        return {
            "ok": False,
            "error": f"could not fetch the {prov} board ({fetch.status.value}): {fetch.detail}",
        }
    board = fetch.jobs

    result: dict[str, Any] = {"ok": True, "company": name, "provider": prov,
                              "slug": board_slug, "count": len(board),
                              "source_status": fetch.status.value,
                              "matched": 0, "saved": 0, "results": []}
    if not board:
        return result

    try:
        scored = score_jobs(cfg, store, board)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    saved = 0
    results: list[dict[str, Any]] = []
    for item in scored[: max(1, limit)]:
        job = item.job
        rec = {
            "title": job.title, "company": job.company, "location": job.location,
            "url": job.url, "remote": bool(job.is_remote), "score": round(item.score, 1),
            "tier": item.tier, "rationale": item.rationale, "saved": False,
        }
        if save and item.tier != "Skip" and job.title and job.company:
            if persist_scored_job(store, item):
                saved += 1
            rec["saved"] = True
        results.append(rec)

    result["matched"] = sum(1 for r in results if r["tier"] != "Skip")
    result["saved"] = saved
    result["results"] = results
    return result


def run(cfg: dict, store, company: str, *, provider: Optional[str] = None,
        slug: Optional[str] = None, save: bool = False, limit: int = 20) -> int:
    """CLI entry: scout a company and print the ranked, profile-matched openings."""
    res = scout(cfg, store, company, provider=provider, slug=slug, save=save, limit=limit)
    if not res.get("ok"):
        print(f"  {res.get('error')}")
        return 1
    tail = f", {res['saved']} saved" if save else ""
    print(f"  {res['company']} [{res['provider']}/{res['slug']}]: {res['count']} on board, "
          f"{res['matched']} match your profile{tail}")
    shown = [r for r in res["results"] if r["tier"] != "Skip"]
    if not shown:
        print("  no openings matched your active profile.")
        return 0
    for r in shown:
        print(f"   {r['score']:>5.1f}  {r['tier']:<7} {r['title']}  ({r['location'] or 'n/a'})")
        print(f"          {r['url']}")
    return 0
