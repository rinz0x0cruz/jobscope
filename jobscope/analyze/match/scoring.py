"""Deterministic fit scoring: the transparent 0-100 ``score_job`` and its skill /
title / comp / location / company / recency sub-scores plus the tiering.

Depends on :mod:`.seniority` (the seniority sub-score) and :mod:`.filters` (the
ghost-job penalty); ``companies`` is imported lazily so the base package stays
network- and data-file-free until a company lookup actually happens.
"""
from __future__ import annotations

import re

from jobscope.core.model import Job, Resume
from .filters import ghost_flags
from .seniority import _seniority_score

SKILL_TARGET = 6  # matching this many of your skills in a JD earns full skill marks

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\+\.#/-]*")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _skill_score(resume: Resume, job_text: str) -> tuple[float, list[str]]:
    jt = job_text.lower()
    hits = []
    for skill in resume.skills:
        s = skill.lower().strip()
        if not s:
            continue
        # word-ish boundary match so "go" doesn't match "google"
        if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", jt):
            hits.append(skill)
    score = min(1.0, len(hits) / float(SKILL_TARGET)) if resume.skills else 0.0
    return score, hits


def _title_score(resume: Resume, job: Job) -> float:
    job_toks = _tokens(job.title)
    if not job_toks:
        return 0.0
    best = 0.0
    candidates = list(resume.titles) + resume.skills[:0]  # titles only
    for rtitle in candidates or []:
        rt = _tokens(rtitle)
        if not rt:
            continue
        overlap = len(job_toks & rt) / len(job_toks | rt)
        best = max(best, overlap)
    # also reward core role words present in title (engineer/security/etc.)
    role_words = {"engineer", "developer", "security", "analyst", "manager",
                  "scientist", "architect", "consultant", "specialist"}
    if job_toks & role_words & {t for rt in candidates for t in _tokens(rt)}:
        best = max(best, 0.5)
    return best


def _comp_score(job: Job, min_salary: float) -> float:
    top = job.salary_max or job.salary_min
    if not top:
        return 0.5  # unknown -> neutral
    if not min_salary:
        return 0.8  # disclosed salary is itself a positive signal
    if top >= min_salary:
        return 1.0
    return max(0.0, top / float(min_salary))


def _location_score(resume: Resume, job: Job, want_remote: bool, prefer: list | None = None,
                    strict: bool = False, country: str = "") -> float:
    # opt-in: a geo-restricted remote role (e.g. "Remote in Ireland") is only
    # "remote" for you if its region matches somewhere you'd work. Global remote
    # and the default (strict off) are unaffected.
    scope = job.remote_scope or ""
    if strict and job.is_remote and scope not in ("", "global"):
        refs = " | ".join([str(p) for p in (prefer or [])]
                          + [resume.location or "", country or ""]).lower()
        if scope.lower() not in refs:
            return 0.4
    # explicit preferred locations win (e.g. ["Remote", "India", "Bengaluru"])
    if prefer:
        loc = (job.location or "").lower()
        for p in prefer:
            pl = (p or "").lower().strip()
            if not pl:
                continue
            if pl in ("remote", "anywhere") and job.is_remote:
                return 1.0
            if pl in loc:
                return 1.0
    if job.is_remote:
        return 1.0 if want_remote else 0.8
    if not resume.location or not job.location:
        return 0.5
    r = resume.location.lower()
    j = job.location.lower()
    if any(part.strip() in j for part in r.split(",") if part.strip()):
        return 0.9
    return 0.3


def _size_signal(company: str, prefer: str) -> tuple[float, str]:
    """Score a company by how well its headcount matches `prefer`.

    Returns (preference_score 0-1, band label). Unknown companies get a neutral
    0.5 with an empty band so size never penalizes an unrecognized employer.
    """
    from jobscope.core import companies
    bigness, band = companies.company_size(company)
    if not band:
        return 0.5, ""
    p = (prefer or "").strip().lower()
    if p in ("small", "startup", "early", "smaller"):
        return 1.0 - bigness, band
    if p in ("mid", "medium", "midsize", "mid-size"):
        dist = abs(companies.SIZE_ORDER.get(band, 2) - companies.SIZE_ORDER["mid"])
        return max(0.0, 1.0 - dist / 2.0), band
    # "large" / "big" / "enterprise" / anything else -> bigger is better
    return bigness, band


def _company_score(job: Job, match_cfg: dict) -> tuple[float, str]:
    """Company desirability: your prefer list wins, else prestige + optional size.

    When `prefer_company_size` is set (large/mid/small), the size preference
    drives the score (60%) with the curated prestige tier as a tie-breaker (40%).
    With no size preference the behaviour is prestige-only (backwards compatible).
    """
    from jobscope.core import companies
    c = (job.company or "").lower()
    for p in match_cfg.get("prefer_companies", []) or []:
        if p and p.lower() in c:
            return 1.0, "preferred"
    prestige, tier = companies.company_quality(job.company)
    prefer_size = (match_cfg.get("prefer_company_size") or "").strip().lower()
    if not prefer_size or prefer_size == "any":
        return prestige, tier
    size_pref, band = _size_signal(job.company, prefer_size)
    if not band:                       # no size data -> prestige alone
        return prestige, tier
    combined = 0.6 * size_pref + 0.4 * prestige
    label = "/".join(x for x in (tier, band) if x) or band
    return combined, label


def _recency_score(job: Job) -> float:
    d = (job.date_posted or "").strip()
    if not d:
        return 0.6
    import datetime as _dt
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            posted = _dt.datetime.strptime(d[: len(fmt) + 2].strip(), fmt)
            age = (_dt.datetime.now(_dt.UTC).replace(tzinfo=None) - posted).days
            if age <= 3:
                return 1.0
            if age <= 7:
                return 0.85
            if age <= 21:
                return 0.6
            return 0.4
        except ValueError:
            continue
    return 0.6


def score_job(job: Job, resume: Resume, match_cfg: dict) -> tuple[float, str, str]:
    """Return (score 0-100, tier, rationale)."""
    weights = match_cfg["weights"]
    job_text = f"{job.title}\n{job.description}"
    skill, skill_hits = _skill_score(resume, job_text)
    company_score, company_tier = _company_score(job, match_cfg)
    parts = {
        "skills": skill,
        "title": _title_score(resume, job),
        "seniority": _seniority_score(resume, job, match_cfg.get("target_seniority", "")),
        "comp": _comp_score(job, match_cfg.get("min_salary", 0) or 0),
        "location": _location_score(resume, job, match_cfg.get("want_remote", True),
                                    match_cfg.get("prefer_locations"),
                                    strict=match_cfg.get("remote_scope_strict", False),
                                    country=match_cfg.get("country", "")),
        "recency": _recency_score(job),
        "company": company_score,
    }
    raw = sum(weights.get(k, 0.0) * v for k, v in parts.items())
    score = 100.0 * raw

    flags = ghost_flags(job)
    if flags:
        score -= float(match_cfg.get("ghost_penalty", 15))
    score = max(0.0, min(100.0, score))

    tiers = match_cfg.get("tiers", {"strong": 75, "good": 55, "stretch": 35})
    if score >= tiers["strong"]:
        tier = "Strong"
    elif score >= tiers["good"]:
        tier = "Good"
    elif score >= tiers["stretch"]:
        tier = "Stretch"
    else:
        tier = "Skip"

    rationale = _rationale(parts, skill_hits, flags, company_tier)
    return round(score, 1), tier, rationale


def _rationale(parts: dict, skill_hits: list[str], flags: list[str], company_tier: str = "") -> str:
    ranked = sorted(parts.items(), key=lambda kv: kv[1], reverse=True)
    top = ", ".join(f"{k} {int(v * 100)}%" for k, v in ranked[:3])
    bits = [f"top: {top}"]
    if company_tier:
        bits.append(f"company: {company_tier}")
    if skill_hits:
        bits.append("skills matched: " + ", ".join(skill_hits[:8]))
    if flags:
        bits.append("⚠ " + "; ".join(flags))
    return " | ".join(bits)
