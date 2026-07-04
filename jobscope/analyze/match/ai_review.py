"""Optional multi-model second opinion on boundary jobs (off by default).

When ``match.ai_score_review`` is on **and** the quorum backend is enabled, a job
whose deterministic score lands within ``match.ai_score_margin`` of a tier cut
gets an independent 0-100 score from quorum's judge. This NEVER changes the
deterministic score/tier and never touches persistence -- it only surfaces a
divergence note on the ``match`` CLI so borderline calls are easy to eyeball.

The job/resume text handed to the judge is framed strictly as DATA (OWASP LLM01);
``ai.score`` returns ``None`` unless quorum is installed and enabled, so this is a
no-op by default.
"""
from __future__ import annotations

from typing import Optional

from jobscope.core.model import Job, Resume

# What the judge weighs when scoring fit (quorum normalizes the weights).
_RUBRIC = {"skill_fit": 0.5, "seniority_fit": 0.3, "relevance": 0.2}


def _tier_of(score: float, tiers: dict) -> str:
    if score >= tiers.get("strong", 75):
        return "Strong"
    if score >= tiers.get("good", 55):
        return "Good"
    if score >= tiers.get("stretch", 35):
        return "Stretch"
    return "Skip"


def near_boundary(score: float, tiers: dict, margin: float) -> bool:
    """True when ``score`` is within ``margin`` points of any tier cut."""
    cuts = (tiers.get("strong", 75), tiers.get("good", 55), tiers.get("stretch", 35))
    return any(abs(score - c) <= margin for c in cuts)


def review_job(cfg: dict, store, job: Job, resume: Resume,
               det_score: float, det_tier: str, tiers: dict) -> Optional[str]:
    """Return a one-line divergence note, or ``None`` (review off / models agree)."""
    from jobscope.core import ai
    task = "Rate 0-100 how well this job posting fits the candidate for a job application."
    candidate = (
        f"CANDIDATE: seniority {resume.seniority or '?'}, ~{resume.years_experience:g}y, "
        f"skills: {', '.join(resume.skills[:25])}.\n"
        f"JOB: {job.title} at {job.company}.\n{(job.description or '')[:1500]}"
    )
    verdict = ai.score(cfg, store, task, candidate, rubric=_RUBRIC)
    if not verdict:
        return None
    ai_score = float(verdict.get("score", 0.0))
    ai_tier = _tier_of(ai_score, tiers)
    if ai_tier == det_tier:
        return None
    return (f"  ~ {job.title} @ {job.company}: deterministic {det_score:g} ({det_tier}) "
            f"vs judge {ai_score:g} ({ai_tier})")
