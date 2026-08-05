"""Quick capture: turn one pasted URL or job description into a previewed Review item.

Preview never writes -- the user confirms first -- and capture never opens a logged-in
session. An auth-walled or otherwise unsupported URL asks for pasted text instead of
trying to work around the site's access controls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobscope.core.model import Job

from . import ats

# A generous ceiling for a real posting; anything larger is a paste accident.
MAX_TEXT_CHARS = 60_000
MIN_TEXT_CHARS = 40

# Pasted postings are not board rows, so they carry their own source. `reconcile_open`
# keys on source, which is what stops a board sweep from closing a captured role.
CAPTURE_SOURCE = "capture"

_LABELS = {
    "company": re.compile(
        r"^[ \t]*(?:company|employer|organisation|organization)[ \t]*[:\-][ \t]*(.+)$",
        re.I | re.M),
    "location": re.compile(
        r"^[ \t]*(?:location|located in|based in|office)[ \t]*[:\-][ \t]*(.+)$",
        re.I | re.M),
    "title": re.compile(
        r"^[ \t]*(?:title|role|position|job title)[ \t]*[:\-][ \t]*(.+)$",
        re.I | re.M),
}


class NeedsPastedText(ValueError):
    """The URL cannot be read without bypassing access controls; ask for the text."""


@dataclass
class CapturePreview:
    """What the user confirms before anything is written."""

    job: Job
    source: str
    score: float = 0.0
    tier: str = ""
    rationale: str = ""
    skip_code: str = ""
    duplicate_of: str = ""
    warnings: list[str] = field(default_factory=list)


def preview(cfg: dict, store, *, url: str = "", text: str = "") -> CapturePreview:
    """Parse one posting and score it without persisting anything."""
    url = (url or "").strip()
    text = (text or "").strip()
    if not url and not text:
        raise ValueError("paste a posting URL or the job description")

    if url and not text:
        job, warnings, source = _from_url(url)
    else:
        job, warnings, source = _from_text(text, url)

    duplicate = store.get_job(job.id)
    existing = getattr(duplicate, "id", "") if duplicate else ""
    result = CapturePreview(job=job, source=source, duplicate_of=existing, warnings=warnings)
    _score_into(cfg, store, result)
    return result


def save(cfg: dict, store, captured: CapturePreview) -> dict:
    """Persist a confirmed capture and refresh the review queue."""
    from jobscope.analyze import review

    job = captured.job
    job.score, job.tier, job.rationale = captured.score, captured.tier, captured.rationale
    is_new = store.upsert_job(job)
    store.update_score(job.id, captured.score, captured.tier, captured.rationale)
    review.sync_reviews(store)
    return {"job_id": job.id, "is_new": is_new, "duplicate_of": captured.duplicate_of}


def _from_url(url: str) -> tuple[Job, list[str], str]:
    board = ats.parse_board_url(url)
    if not board:
        raise NeedsPastedText(
            "that URL is not a supported public job board -- paste the job description instead",
        )
    provider, slug = board
    jobs = ats.fetch_company(slug, provider, slug)
    for job in jobs:
        if job.url.split("?")[0] == url.split("?")[0]:
            return job.ensure_id(), [], "url"
    raise NeedsPastedText(
        "that posting was not on the board (it may be closed) -- paste the description instead",
    )


def _from_text(text: str, url: str) -> tuple[Job, list[str], str]:
    if len(text) < MIN_TEXT_CHARS:
        raise ValueError("that is too short to be a job description")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"that is longer than {MAX_TEXT_CHARS} characters")

    warnings: list[str] = []
    title = _label(text, "title") or _first_line(text)
    company = _label(text, "company")
    location = _label(text, "location")
    if not company:
        warnings.append("could not find a company name -- set it before saving")
    if not location:
        warnings.append("could not find a location -- set it before saving")

    job = Job(
        source=CAPTURE_SOURCE, title=title, company=company, location=location,
        url=url, description=text,
    ).ensure_id()
    return job, warnings, "text"


def _score_into(cfg: dict, store, result: CapturePreview) -> None:
    """Attach deterministic score/tier, or say plainly why it could not be scored."""
    from jobscope.analyze import review

    try:
        scored = review.score_jobs(cfg, store, [result.job])[0]
    except ValueError:
        result.warnings.append("no resume imported yet, so this was not scored")
        return
    result.score = scored.score
    result.tier = scored.tier
    result.rationale = scored.rationale
    result.skip_code = scored.skip_code


def _label(text: str, key: str) -> str:
    found = _LABELS[key].search(text)
    return found.group(1).strip() if found else ""


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""
