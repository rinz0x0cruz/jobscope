"""The match orchestrator: score every stored job against your résumé(s), apply
filters, optionally AI-tiebreak the ambiguous leakers, and persist the results.

``ai`` and ``classify`` are imported lazily inside :func:`run` (never at module
load) -- ``classify`` imports ``SENIORITY_RANK`` from this package at load time,
so keeping the import lazy is what avoids the match<->classify cycle.
"""
from __future__ import annotations

from .experience import required_experience_years
from .filters import apply_filters
from .routing import LEAN_DECISIVE, _job_lean, _resume_lean, select_base


def run(cfg: dict, store) -> int:
    """Score every stored job against your resume(s), applying filters."""
    resumes = store.list_resumes()
    if not resumes:
        print("  no resume found. Run `python -m jobscope resume import <path>` first.")
        return 1
    match_cfg = dict(cfg["match"])
    match_cfg["want_remote"] = cfg["search"].get("is_remote", True)
    match_cfg["country"] = cfg["search"].get("country_indeed", "")
    fcfg = cfg.get("filters", {})
    multi = len(resumes) > 1

    def _score(job):
        s, t, r, b = select_base(job, resumes, match_cfg)
        reason = apply_filters(job, fcfg)
        if reason:
            return s, "Skip", f"⛔ {reason} | {r}", b, True
        return s, t, r, b, False

    # Optional AI/quorum tie-breaker: only for postings with NO deterministic seniority
    # cue that still land non-Skip (i.e. actually leaking). No-op unless ai.enabled.
    from .. import ai
    ai_on = ai.available(cfg) and match_cfg.get("ai_seniority_tiebreak", True)
    max_calls = int(match_cfg.get("ai_tiebreak_max_calls", 0) or 0)
    classify = None
    if ai_on:
        from ..classify import classify_seniority as classify
    ai_calls = 0
    ai_used = 0

    jobs = store.jobs(order_by_score=False)
    counts = {"Strong": 0, "Good": 0, "Stretch": 0, "Skip": 0}
    blocked = 0
    for job in jobs:
        score, tier, rationale, base, was_blocked = _score(job)
        if (ai_on and not was_blocked and not (job.ai_seniority or "")
                and required_experience_years(job) is None
                and (max_calls == 0 or ai_calls < max_calls)):
            ai_calls += 1
            c = classify(cfg, store, job)
            if c:
                job.ai_seniority = c["level"]
                job.ai_required_years = c["required_years"]
                store.update_ai_seniority(job.id, job.ai_seniority, job.ai_required_years)
                score, tier, rationale, base, was_blocked = _score(job)
                rationale = f"{rationale} · AI:{job.ai_seniority}~{int(job.ai_required_years)}y"
                disc = c.get("discipline")
                if (multi and disc in ("technical", "advisory")
                        and abs(_job_lean(job)) < LEAN_DECISIVE):
                    # lean-ambiguous posting: let the AI discipline break the routing tie
                    pick = max if disc == "technical" else min
                    base = pick(resumes, key=lambda nr: _resume_lean(nr[1]))[0]
                    rationale = f"{rationale} · AI-route:{disc}"
                ai_used += 1
        if was_blocked:
            blocked += 1
        store.update_score(job.id, score, tier, rationale, resume_base=base if multi else "")
        counts[tier] += 1
    store.log_run("match", len(jobs), "ok")
    base_note = f" using {len(resumes)} base resumes" if multi else ""
    ai_note = f", AI re-checked {ai_used}" if ai_used else ""
    print(f"  scored {len(jobs)} jobs{base_note} -> "
          f"Strong {counts['Strong']}, Good {counts['Good']}, "
          f"Stretch {counts['Stretch']}, Skip {counts['Skip']}"
          + (f" ({blocked} filtered)" if blocked else "") + ai_note)
    return 0
