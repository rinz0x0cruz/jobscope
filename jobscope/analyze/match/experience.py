"""Experience-requirement extraction: the minimum years of experience a posting
implies, combining the seniority ladder with explicit "N+ years" phrases.

Depends on :mod:`.seniority` (a leaf); imported by :mod:`.filters` for the
``max_years_experience`` cap and by the ``run`` orchestrator.
"""
from __future__ import annotations

import re
from typing import Optional

from jobscope.core.model import Job
from .seniority import _job_seniority

# Rough minimum years of experience implied by a seniority word in the title.
_SENIORITY_MIN_YEARS = {0: 0, 1: 0, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10, 7: 12, 8: 15}


def required_experience_years(job: Job) -> Optional[float]:
    """Best-effort minimum years of experience a posting asks for.

    Combines the seniority implied by the title (Senior ~4y, Staff ~6y, Principal
    ~8y, ...) with explicit "N+ years" / "N-M years" / "N years of experience"
    phrases in the text. Returns None when the posting gives no experience signal.
    Deliberately conservative (takes the highest stated bar) so an experience cap
    doesn't leak clearly-too-senior roles through.
    """
    title = job.title or ""
    text = f"{title}\n{job.description or ''}".lower().replace("\u2013", "-").replace("\u2014", "-")
    nums: list[int] = []
    for m in re.finditer(r"(?<![\d-])(\d{1,2})\s*\+\s*(?:years?|yrs?)", text):            # "5+ years"
        nums.append(int(m.group(1)))
    for m in re.finditer(r"(?<![\d-])(\d{1,2})\s*(?:-|\u2013|to)\s*\d{1,2}\s*(?:years?|yrs?)", text):  # "3-5 years"
        nums.append(int(m.group(1)))                                          # lower bound
    for m in re.finditer(r"(?<![\d-])(\d{1,2})\s*\+?\s*(?:years?|yrs?)[^.\n]{0,30}(?:experience|exp\b)", text):        # "5 years ... experience"
        nums.append(int(m.group(1)))
    for m in re.finditer(r"(?:at\s+least|minimum(?:\s+of)?|min(?:\.|\s+of)?)\s+(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text):  # "minimum 5 years"
        nums.append(int(m.group(1)))
    for m in re.finditer(r"(?<![\d-])(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:required|minimum|min\b)", text):  # "5 years required"
        nums.append(int(m.group(1)))
    for m in re.finditer(r"(?:over|more than)\s+(\d{1,2})\s*(?:years?|yrs?)", text):    # "over 5 years"
        nums.append(int(m.group(1)))
    for m in re.finditer(r"(?<![\d-])(\d{1,2})\s*(?:or more|plus)\s+(?:years?|yrs?)", text):  # "5 or more years"
        nums.append(int(m.group(1)))
    explicit = max((n for n in nums if 1 <= n <= 25), default=None)
    qualitative = 4 if re.search(
        r"\bseasoned\s+(?:subject\s+matter\s+expert|experience|knowledge)\b",
        text,
    ) else None

    rank = _job_seniority(job)
    tmin = _SENIORITY_MIN_YEARS.get(rank) if rank is not None else None
    ai_years = getattr(job, "ai_required_years", None)

    vals = [v for v in (explicit, qualitative, tmin, ai_years) if v is not None]
    return float(max(vals)) if vals else None
