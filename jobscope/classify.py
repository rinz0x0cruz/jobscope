"""Optional AI seniority classifier for postings with no deterministic level signal.

Runs only when ``ai.enabled`` (and routes through quorum automatically when
``quorum.enabled`` -- see ai.chat). Returns a normalized level + estimated required
years, or ``None`` when AI is unavailable or the reply can't be parsed. The caller
(match.run) uses this ONLY for the ambiguous, non-Skip bucket so cost stays bounded.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import ai
from .match import SENIORITY_RANK
from .model import Job

_VALID = ("intern", "junior", "mid", "senior", "staff", "principal", "lead", "director")

_SYSTEM = (
    "You are a precise job-seniority classifier. Judge the level from the SCOPE and "
    "RESPONSIBILITIES of the posting, not just the title. Reply with STRICT JSON only, "
    "no prose: {\"level\": <one of "
    + "|".join(_VALID)
    + ">, \"required_years\": <integer 0-20>}."
)


def classify_seniority(cfg: dict, store, job: Job) -> Optional[dict]:
    """Ask the AI/quorum layer for {level, required_years}. None if off/failed/empty."""
    title = (job.title or "").strip()
    desc = (job.description or "").strip()[:1500]
    if not title and not desc:
        return None
    user = f"Title: {title}\n\nDescription:\n{desc or '(none)'}"
    raw = ai.chat(cfg, store, _SYSTEM, user, temperature=0.0)
    if not raw:
        return None
    return _parse(raw)


def _parse(raw: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    level = str(data.get("level", "")).strip().lower()
    if level not in _VALID or level not in SENIORITY_RANK:
        return None
    try:
        years = float(data.get("required_years"))
    except (TypeError, ValueError):
        years = float(SENIORITY_RANK.get(level, 0) * 2)  # fall back from the level
    years = max(0.0, min(20.0, years))
    return {"level": level, "required_years": years}
