"""Aggregate skill-gap analysis -> a concrete learning plan.

Deterministic: across your worth-considering jobs (Strong/Good/Stretch), find the
skills that recur in job descriptions but are absent from *any* of your resumes,
ranked by how many jobs each would help unlock. No AI, no network.
"""
from __future__ import annotations

import re

from .resume import SKILL_LEXICON

_TIERS_DEFAULT = {"Strong", "Good", "Stretch"}


def skill_gap(store, top: int = 15, tiers: set[str] | None = None):
    """Return (jobs_considered, [(skill, job_count, [example_companies])])."""
    tiers = tiers or _TIERS_DEFAULT
    have = set()
    for _name, resume in store.list_resumes():
        have |= {s.lower() for s in resume.skills}

    counts: dict[str, int] = {}
    examples: dict[str, set[str]] = {}
    considered = 0
    for job in store.jobs(order_by_score=True):
        if job.tier not in tiers:
            continue
        considered += 1
        jd = f"{job.title}\n{job.description}".lower()
        for skill in SKILL_LEXICON:
            if skill in have:
                continue
            if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", jd):
                counts[skill] = counts.get(skill, 0) + 1
                examples.setdefault(skill, set()).add(job.company)

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    return considered, [(s, c, sorted(x for x in examples[s] if x)[:3]) for s, c in ranked]


def run(cfg: dict, store, top: int = 15) -> int:
    considered, gaps = skill_gap(store, top=top)
    if considered == 0:
        print("  nothing to analyze yet. Run `scan` + `match` first.")
        return 0
    if not gaps:
        print(f"  no skill gaps across {considered} jobs -- your resumes already cover the market.")
        return 0
    print(f"  Skill-gap learning plan (across {considered} Strong/Good/Stretch jobs):\n")
    print(f"  {'SKILL':<28} {'JOBS':>4}  EXAMPLE COMPANIES")
    print("  " + "-" * 68)
    for skill, count, companies in gaps:
        print(f"  {skill:<28} {count:>4}  {', '.join(companies)[:38]}")
    print("\n  Learning the top items unlocks the most additional matches "
          "(add them to a resume only if genuinely true).")
    return 0
