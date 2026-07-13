"""On-demand company scout: fetch a company's public ATS board (Greenhouse / Lever /
Ashby) and score its openings against the *active* search profile's résumé.

Unlike the batch ``scan`` (config-listed companies), this resolves a company by
name at call time -- known slug, an explicit ``provider|slug`` override, or a
best-effort probe. It needs the network, so it runs under local ``jobscope serve``
or the CLI, never on the static site. Deterministic scoring only (AI off).
"""
from __future__ import annotations

from typing import Any, Optional

from jobscope.ingest import ats


def _active_resume(cfg: dict, store):
    """The résumé the active profile points at, falling back to the primary."""
    from jobscope.analyze import profile as _profile

    prof = _profile.load(cfg) or {}
    rname = prof.get("resume")
    resume = store.get_resume(rname) if rname else None
    return resume if resume is not None else store.get_resume()


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

    try:
        board = ats.fetch_company(name, prov, board_slug)
    except Exception as exc:  # noqa: BLE001 - surface a friendly error to the caller
        return {"ok": False, "error": f"could not fetch the {prov} board: {str(exc)[:120]}"}

    result: dict[str, Any] = {"ok": True, "company": name, "provider": prov,
                              "slug": board_slug, "count": len(board),
                              "matched": 0, "saved": 0, "results": []}
    if not board:
        return result

    resume = _active_resume(cfg, store)
    if resume is None:
        return {"ok": False, "error": "no résumé imported -- run `resume import <path>` first"}

    from jobscope.analyze import profile as _profile
    from jobscope.analyze.match.filters import apply_filters
    from jobscope.analyze.match.routing import select_base

    prof = _profile.load(cfg) or {}
    search = cfg.get("search", {}) or {}
    match_cfg = dict(cfg.get("match", {}))
    match_cfg["want_remote"] = bool(prof.get("remote", search.get("is_remote", True)))
    match_cfg["country"] = search.get("country_indeed", "")
    fcfg = cfg.get("filters", {}) or {}
    resumes = [(prof.get("resume") or "default", resume)]

    scored: list[tuple[float, str, str, Any]] = []
    for job in board:
        s, tier, rationale, _base = select_base(job, resumes, match_cfg)
        reason = apply_filters(job, fcfg)
        if reason:
            tier, rationale = "Skip", f"{reason} | {rationale}"
        scored.append((float(s), tier, rationale, job))
    scored.sort(key=lambda x: x[0], reverse=True)

    saved = 0
    results: list[dict[str, Any]] = []
    for score, tier, rationale, job in scored[: max(1, limit)]:
        rec = {
            "title": job.title, "company": job.company, "location": job.location,
            "url": job.url, "remote": bool(job.is_remote), "score": round(score, 1),
            "tier": tier, "rationale": rationale, "saved": False,
        }
        if save and tier != "Skip" and job.title and job.company:
            if store.upsert_job(job):
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
