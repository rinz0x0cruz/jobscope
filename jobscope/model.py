"""Core data models for jobscope.

These are plain dataclasses used across scraping, matching, enrichment, and
application prep. Persistence lives in :mod:`jobscope.store`; anything that needs
to be stored is serialized to/from these shapes there.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def slugify(value: str) -> str:
    """Lowercase, hyphenated, filesystem-safe token."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def job_id(source: str, title: str, company: str, url: str = "") -> str:
    """Stable id for a job.

    Prefer the canonical URL when present (dedupes reposts across runs); fall
    back to a hash of site+title+company so rows are still deterministic.
    """
    basis = url.strip() if url else f"{source}|{title}|{company}".lower()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


# Common country/region codes -> canonical name, for remote-scope normalization.
_REMOTE_REGION_CODES = {
    "in": "India", "ind": "India", "us": "United States", "usa": "United States",
    "uk": "United Kingdom", "gbr": "United Kingdom", "ie": "Ireland",
    "ca": "Canada", "can": "Canada", "au": "Australia", "aus": "Australia",
    "sg": "Singapore", "de": "Germany", "deu": "Germany", "fr": "France",
    "nl": "Netherlands",
}
# Acronyms that stay upper-case rather than title-cased (e.g. "remote in EMEA").
_REMOTE_ACRONYMS = {"US", "UK", "EU", "EMEA", "APAC", "LATAM"}
# Leading/trailing junk to peel off a captured region (punctuation, brackets, dashes).
_REGION_STRIP = " \t.,:;/&()[]-\u2013\u2014"
# Work-mode words that are not a place -- dropped from a captured region so noise
# like "Remote-first" or "US-Remote" doesn't turn into a fake region.
_REMOTE_FILLER = {"remote", "remotely", "anywhere", "wfh", "hybrid", "onsite",
                  "on-site", "based", "and", "or", "the", "first", "friendly",
                  "ok", "optional", "possible", "eligible"}


def _normalize_region(region: str) -> str:
    """Canonicalize a raw region token: strip work-mode words, map codes/acronyms.

    Returns "" when nothing place-like remains (the caller treats that as global).
    """
    region = (region or "").strip().strip(_REGION_STRIP).strip()
    if not region:
        return ""
    # Multi-region tokens like "US/Canada" -> normalize each side, dedupe.
    if "/" in region:
        parts = [p for p in (_normalize_region(x) for x in region.split("/")) if p]
        return "/".join(dict.fromkeys(parts))
    # Drop work-mode filler words and any trailing "-remote"/"-wfh" on a word.
    words = []
    for w in region.split():
        w = re.sub(r"[-\u2013\u2014]?(?:remote|wfh)$", "", w, flags=re.I)
        wc = w.strip(_REGION_STRIP)
        if wc and wc.lower() not in _REMOTE_FILLER:
            words.append(wc)
    if not words or len(words) > 3:          # empty or too long to be a clean place
        return ""
    low = " ".join(words).lower()
    if low in _REMOTE_REGION_CODES:
        return _REMOTE_REGION_CODES[low]
    out = []
    for w in words:
        if w.lower() in _REMOTE_REGION_CODES:
            out.append(_REMOTE_REGION_CODES[w.lower()])
        elif w.upper() in _REMOTE_ACRONYMS:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def derive_remote_scope(location: str, title: str, is_remote: bool) -> str:
    """Classify a remote posting's reach from its *location*.

    Returns "" when the role is not remote/unknown, "global" for remote-anywhere,
    or a normalized region for geo-restricted remote. Examples:
    "Remote in Ireland" -> "Ireland", "Remote - India" -> "India",
    "Remote (US)" -> "United States", a bare "Remote" -> "global", and an
    is_remote role whose location names a place ("Dublin, …, Ireland") -> "Ireland".

    Only the location is parsed (never the title), so job-title words can't leak
    in; the "in" separator is word-anchored so "India" isn't read as "in" + "dia".
    """
    if not is_remote:
        return ""
    loc = location or ""
    m = re.search(r"remote\s*(?:in\b|[-\u2013\u2014:,(])\s*([A-Za-z .&/]+)", loc, re.I)
    if m:
        region = _normalize_region(m.group(1))
        if region:
            return region
    if "," in loc:
        region = _normalize_region(loc.split(",")[-1])
        if region:
            return region
    return "global"


@dataclass
class Resume:
    """Structured resume parsed from Markdown / JSON Resume / PDF."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)          # roles held, for title matching
    experiences: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    years_experience: float = 0.0
    seniority: str = ""                                      # intern/junior/mid/senior/staff/principal
    raw_text: str = ""
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Resume":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class Job:
    """A single normalized job posting (superset of the JobSpy schema)."""

    id: str = ""
    source: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    is_remote: bool = False
    remote_scope: str = ""            # "" = not remote/unknown; "global" = remote anywhere; else a region e.g. "Ireland"
    raw_is_remote: Optional[bool] = None   # raw JobSpy flag preserved; None when not from JobSpy (e.g. ATS)
    url: str = ""
    description: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_interval: str = ""                                # yearly/monthly/hourly...
    currency: str = ""
    job_type: str = ""                                       # fulltime/contract/intern...
    company_industry: str = ""
    company_url: str = ""
    date_posted: str = ""
    # scoring (filled by match.py)
    score: float = 0.0
    tier: str = ""                                           # Strong/Good/Stretch/Skip
    rationale: str = ""
    resume_base: str = ""                                    # which base resume scored best
    first_seen: str = ""
    last_seen: str = ""
    status: str = "open"                                     # open | closed (taken down)
    closed_at: str = ""                                      # when it left the source board

    def ensure_id(self) -> "Job":
        if not self.id:
            self.id = job_id(self.source, self.title, self.company, self.url)
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class Contact:
    """A legit-only referral lead (public data + search links; no PII harvesting)."""

    id: str = ""
    company: str = ""
    name: str = ""
    title: str = ""
    source: str = ""                                         # github/team-page/search
    profile_url: str = ""
    search_url: str = ""
    outreach: str = ""                                       # AI-drafted (optional)
    first_seen: str = ""


@dataclass
class Application:
    """Tracks a prepared application through review -> submit -> follow-up."""

    job_id: str = ""
    status: str = "new"                                      # new/prepared/applied/interview/rejected/offer
    package_dir: str = ""
    resume_path: str = ""
    cover_path: str = ""
    applied_at: str = ""
    notes: str = ""
    updated: str = ""


# Canonical application statuses (mirrors career-ops' states.yml idea).
STATUSES = ["new", "prepared", "applied", "interview", "rejected", "offer", "skipped"]
