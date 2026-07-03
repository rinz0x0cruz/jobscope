"""Seniority inference: map a posting's title / structured ``job_level`` / numeric
level codes to a rank, and score how a résumé's level fits the role.

Leaf module of the :mod:`jobscope.match` package -- it imports only the data
model, so ``SENIORITY_RANK`` (used by ``resume``/``classify`` at import time)
stays cheap to import and can never form a cycle.
"""
from __future__ import annotations

import re
from typing import Optional

from jobscope.core.model import Job, Resume

# seniority ladder -> rank
SENIORITY_RANK = {
    "intern": 0, "internship": 0,
    "junior": 1, "jr": 1, "entry": 1, "associate": 1, "new grad": 1, "graduate": 1,
    "mid": 2, "intermediate": 2,
    "senior": 3, "sr": 3,
    "staff": 4, "lead": 4, "principal": 5, "architect": 5,
    "director": 6, "head": 6, "vp": 7, "chief": 8,
}


def _title_seniority(title: str) -> Optional[int]:
    t = f" {title.lower()} "
    best = None
    for word, rank in SENIORITY_RANK.items():
        if f" {word} " in t or f" {word}," in t or t.strip().startswith(word + " "):
            best = rank if best is None else max(best, rank)
    return best


# LinkedIn "Seniority level" (via JobSpy `job_level`) -> rank. Only the confident
# buckets; "mid-senior level" is intentionally omitted (too broad to trust).
_JOB_LEVEL_RANK = {
    "internship": 0, "intern": 0,
    "entry level": 1, "entry": 1, "associate": 1,
    "director": 6, "executive": 7,
}

# Numeric / company level codes in a title -> rank (highest first; word-anchored).
_NUMERIC_LEVEL = [
    (re.compile(r"\b(?:l[6-9]|ic[6-9])\b", re.I), 5),
    (re.compile(r"\b(?:l5|ic5|level\s*5)\b", re.I), 4),
    (re.compile(r"\b(?:l4|ic4|iv|level\s*4)\b", re.I), 3),
    (re.compile(r"\b(?:iii|l3|ic3|level\s*3)\b", re.I), 3),
    (re.compile(r"\b(?:ii|l2|ic2|level\s*2)\b", re.I), 2),
    (re.compile(r"\b(?:l1|ic1|level\s*1)\b", re.I), 1),
]


def _job_seniority(job: Job) -> Optional[int]:
    """Best seniority rank from the title, the structured ``job_level``, and numeric
    level codes (Sr., II/III, L5, IC4). Highest signal wins; None when the posting
    gives no seniority cue at all."""
    ranks: list[int] = []
    title = job.title or ""
    for variant in (title, re.sub(r"[./]", " ", title)):
        r = _title_seniority(variant)
        if r is not None:
            ranks.append(r)
    jl = (getattr(job, "job_level", "") or "").lower()
    for key, rank in _JOB_LEVEL_RANK.items():
        if key in jl:
            ranks.append(rank)
            break
    for rx, rank in _NUMERIC_LEVEL:
        if rx.search(title):
            ranks.append(rank)
            break
    ai_lvl = SENIORITY_RANK.get((getattr(job, "ai_seniority", "") or "").lower())
    if ai_lvl is not None:
        ranks.append(ai_lvl)
    return max(ranks) if ranks else None


def _seniority_score(resume: Resume, job: Job, target: str = "") -> float:
    # `target` (config match.target_seniority) overrides the resume-inferred level
    # when set. The penalty is ASYMMETRIC: a role more senior than you (you'd be
    # under-qualified) is punished hard; being over-qualified is only mildly damped.
    want = SENIORITY_RANK.get((target or resume.seniority or "").lower())
    have = _job_seniority(job)
    if want is None or have is None:
        return 0.6  # unknown -> mildly neutral
    diff = have - want          # > 0 = role is more senior than you
    if diff <= 0:
        return 1.0 if diff >= -1 else 0.85
    if diff == 1:
        return 0.7
    if diff == 2:
        return 0.4
    return 0.15
