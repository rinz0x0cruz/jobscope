"""Deterministic job-fit scoring (the core "80% logic").

`score_job` returns a transparent 0-100 score plus a tier and a short rationale,
computed only from the resume and the posting -- no network, no AI. Weights are
configurable (see config `match.weights`). A scam/ghost-job penalty mirrors the
idea behind career-ops' "Block G" legitimacy check.
"""
from __future__ import annotations

import re
from typing import Optional

from .model import Job, Resume

# seniority ladder -> rank
SENIORITY_RANK = {
    "intern": 0, "internship": 0,
    "junior": 1, "jr": 1, "entry": 1, "associate": 1, "new grad": 1, "graduate": 1,
    "mid": 2, "intermediate": 2,
    "senior": 3, "sr": 3,
    "staff": 4, "lead": 4, "principal": 5, "architect": 5,
    "director": 6, "head": 6, "vp": 7, "chief": 8,
}

SKILL_TARGET = 6  # matching this many of your skills in a JD earns full skill marks

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\+\.#/-]*")

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



def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _title_seniority(title: str) -> Optional[int]:
    t = f" {title.lower()} "
    best = None
    for word, rank in SENIORITY_RANK.items():
        if f" {word} " in t or f" {word}," in t or t.strip().startswith(word + " "):
            best = rank if best is None else max(best, rank)
    return best


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


def _seniority_score(resume: Resume, job: Job) -> float:
    want = SENIORITY_RANK.get((resume.seniority or "").lower())
    have = _title_seniority(job.title)
    if want is None or have is None:
        return 0.6  # unknown -> mildly neutral
    dist = abs(have - want)
    if dist == 0:
        return 1.0
    if dist == 1:
        return 0.75
    if dist == 2:
        return 0.45
    return 0.2


def _comp_score(job: Job, min_salary: float) -> float:
    top = job.salary_max or job.salary_min
    if not top:
        return 0.5  # unknown -> neutral
    if not min_salary:
        return 0.8  # disclosed salary is itself a positive signal
    if top >= min_salary:
        return 1.0
    return max(0.0, top / float(min_salary))


def _location_score(resume: Resume, job: Job, want_remote: bool) -> float:
    if job.is_remote:
        return 1.0 if want_remote else 0.8
    if not resume.location or not job.location:
        return 0.5
    r = resume.location.lower()
    j = job.location.lower()
    if any(part.strip() in j for part in r.split(",") if part.strip()):
        return 0.9
    return 0.3


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


def score_job(job: Job, resume: Resume, match_cfg: dict) -> tuple[float, str, str]:
    """Return (score 0-100, tier, rationale)."""
    weights = match_cfg["weights"]
    job_text = f"{job.title}\n{job.description}"
    skill, skill_hits = _skill_score(resume, job_text)
    parts = {
        "skills": skill,
        "title": _title_score(resume, job),
        "seniority": _seniority_score(resume, job),
        "comp": _comp_score(job, match_cfg.get("min_salary", 0) or 0),
        "location": _location_score(resume, job, match_cfg.get("want_remote", True)),
        "recency": _recency_score(job),
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

    rationale = _rationale(parts, skill_hits, flags)
    return round(score, 1), tier, rationale


def _rationale(parts: dict, skill_hits: list[str], flags: list[str]) -> str:
    ranked = sorted(parts.items(), key=lambda kv: kv[1], reverse=True)
    top = ", ".join(f"{k} {int(v * 100)}%" for k, v in ranked[:3])
    bits = [f"top: {top}"]
    if skill_hits:
        bits.append("skills matched: " + ", ".join(skill_hits[:8]))
    if flags:
        bits.append("⚠ " + "; ".join(flags))
    return " | ".join(bits)


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
    max_age = fcfg.get("max_age_days", 0) or 0
    if max_age:
        age = _age_days(job)
        if age is not None and age > max_age:
            return f"older than {max_age}d ({age}d)"
    return None


def select_base(job: Job, resumes: list, match_cfg: dict) -> tuple[float, str, str, str]:
    """Score the job against each base resume; return the best (score, tier, rationale, name)."""
    best_score, best_tier, best_rat, best_name = 0.0, "Skip", "no resume", ""
    first = True
    for name, resume in resumes:
        score, tier, rationale = score_job(job, resume, match_cfg)
        if first or score > best_score:
            best_score, best_tier, best_rat, best_name = score, tier, rationale, name
            first = False
    return best_score, best_tier, best_rat, best_name


def run(cfg: dict, store) -> int:
    """Score every stored job against your resume(s), applying filters."""
    resumes = store.list_resumes()
    if not resumes:
        print("  no resume found. Run `python -m jobscope resume import <path>` first.")
        return 1
    match_cfg = dict(cfg["match"])
    match_cfg["want_remote"] = cfg["search"].get("is_remote", True)
    fcfg = cfg.get("filters", {})
    multi = len(resumes) > 1

    jobs = store.jobs(order_by_score=False)
    counts = {"Strong": 0, "Good": 0, "Stretch": 0, "Skip": 0}
    blocked = 0
    for job in jobs:
        score, tier, rationale, base = select_base(job, resumes, match_cfg)
        reason = apply_filters(job, fcfg)
        if reason:
            tier = "Skip"
            rationale = f"⛔ {reason} | {rationale}"
            blocked += 1
        store.update_score(job.id, score, tier, rationale, resume_base=base if multi else "")
        counts[tier] += 1
    store.log_run("match", len(jobs), "ok")
    base_note = f" using {len(resumes)} base resumes" if multi else ""
    print(f"  scored {len(jobs)} jobs{base_note} -> "
          f"Strong {counts['Strong']}, Good {counts['Good']}, "
          f"Stretch {counts['Stretch']}, Skip {counts['Skip']}"
          + (f" ({blocked} filtered)" if blocked else ""))
    return 0

