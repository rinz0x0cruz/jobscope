"""Hard filters and legitimacy detectors: block-lists, clearance/citizenship and
no-sponsorship signals, the experience cap, posting age, and ghost/scam flags.

``apply_filters`` returns a block reason (or None). Depends on :mod:`.experience`
for the years cap; the signal lists live here and are re-exported by the package.
"""
from __future__ import annotations

from typing import Optional

from jobscope.core.model import Job
from .experience import required_experience_years

GHOST_SIGNALS = [
    "commission only", "commission-only", "unlimited earning", "be your own boss",
    "no experience necessary", "immediate start", "work from home opportunity",
    "earn up to", "100% remote sales", "quick money", "financial freedom",
]

# Phrases that imply US work-authorization / security-clearance barriers.
CLEARANCE_SIGNALS = [
    "security clearance", "active clearance", "ts/sci", "top secret", "secret clearance",
    "clearance required", "must have clearance", "polygraph", "public trust",
    "us citizen", "u.s. citizen", "usc only", "citizenship required",
    "must be a us citizen", "must be a u.s. citizen", "citizen or green card",
]
# Phrases that imply the employer will NOT sponsor a visa.
NO_SPONSORSHIP_SIGNALS = [
    "no sponsorship", "not able to sponsor", "unable to sponsor", "will not sponsor",
    "cannot sponsor", "can not sponsor", "can't sponsor", "won't sponsor", "do not sponsor",
    "does not provide sponsorship", "not eligible for sponsorship",
    "without sponsorship", "no visa sponsorship", "sponsorship is not available",
    "authorized to work in the us without", "authorized to work in the united states without",
]


def ghost_flags(job: Job) -> list[str]:
    """Heuristic scam / ghost-job signals (deterministic)."""
    flags = []
    desc = (job.description or "").lower()
    if desc and len(desc) < 200:
        flags.append("very short description")
    for sig in GHOST_SIGNALS:
        if sig in desc:
            flags.append(f"buzzphrase: {sig}")
    if not job.description and not (job.salary_min or job.salary_max):
        flags.append("no description and no salary")
    if job.title and job.title.lower().count("!") >= 1:
        flags.append("clickbait title")
    return flags


def clearance_flags(job: Job) -> list[str]:
    """Return matched clearance/citizenship phrases (US work-auth barriers)."""
    text = f"{job.title}\n{job.description}".lower()
    return [sig for sig in CLEARANCE_SIGNALS if sig in text]


def no_sponsorship(job: Job) -> bool:
    text = f"{job.title}\n{job.description}".lower()
    return any(sig in text for sig in NO_SPONSORSHIP_SIGNALS)


def _age_days(job: Job) -> Optional[int]:
    d = (job.date_posted or "").strip()
    if not d:
        return None
    import datetime as _dt
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            posted = _dt.datetime.strptime(d[: len(fmt) + 2].strip(), fmt)
            return (_dt.datetime.now(_dt.UTC).replace(tzinfo=None) - posted).days
        except ValueError:
            continue
    return None


def apply_filters(job: Job, fcfg: dict) -> Optional[str]:
    """Return a block reason if the job should be filtered to Skip, else None."""
    company = (job.company or "").lower()
    title = (job.title or "").lower()
    blob = f"{title}\n{(job.description or '').lower()}"

    for c in fcfg.get("block_companies", []):
        if c and c.lower() in company:
            return f"blocked company ({c})"
    for kw in fcfg.get("block_title_keywords", []):
        if kw and kw.lower() in title:
            return f"blocked title keyword ({kw})"
    for kw in fcfg.get("block_keywords", []):
        if kw and kw.lower() in blob:
            return f"blocked keyword ({kw})"
    if fcfg.get("exclude_clearance"):
        cf = clearance_flags(job)
        if cf:
            return f"clearance/citizenship required ({cf[0]})"
    if fcfg.get("needs_sponsorship") and no_sponsorship(job):
        return "no visa sponsorship"
    cap = fcfg.get("max_years_experience", 0) or 0
    if cap:
        req = required_experience_years(job)
        if req is not None and req > cap:
            return f"needs ~{int(req)}y experience (cap {cap}y)"
    max_age = fcfg.get("max_age_days", 0) or 0
    if max_age:
        age = _age_days(job)
        if age is not None and age > max_age:
            return f"older than {max_age}d ({age}d)"
    return None
