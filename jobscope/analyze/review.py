"""Shared deterministic scoring for Scout and company-monitor review queues."""
from __future__ import annotations

from dataclasses import dataclass

from jobscope.core.model import Job
from jobscope.core.store.base import now_iso


REVIEW_CLEAR_MARKER = "reviews:cleared_before"


@dataclass(slots=True)
class ScoredJob:
    job: Job
    score: float
    tier: str
    rationale: str
    resume_base: str


def active_resume(cfg: dict, store):
    from jobscope.analyze import profile

    current = profile.load(cfg) or {}
    resume_name = current.get("resume")
    resume = store.get_resume(resume_name) if resume_name else None
    return current, resume if resume is not None else store.get_resume()


def score_jobs(cfg: dict, store, jobs: list[Job]) -> list[ScoredJob]:
    """Score jobs against the active profile using the normal filters and router."""
    from jobscope.analyze.match.filters import apply_filters
    from jobscope.analyze.match.routing import select_base

    profile, resume = active_resume(cfg, store)
    if resume is None:
        raise ValueError("no résumé imported -- run `resume import <path>` first")
    search = cfg.get("search", {}) or {}
    match_cfg = dict(cfg.get("match", {}))
    match_cfg["want_remote"] = bool(profile.get("remote", search.get("is_remote", True)))
    match_cfg["country"] = search.get("country_indeed", "")
    filters = cfg.get("filters", {}) or {}
    resumes = [(profile.get("resume") or "default", resume)]

    scored: list[ScoredJob] = []
    for job in jobs:
        score, tier, rationale, resume_base = select_base(job, resumes, match_cfg)
        reason = apply_filters(job, filters)
        if reason:
            tier, rationale = "Skip", f"{reason} | {rationale}"
        scored.append(ScoredJob(job, float(score), tier, rationale, resume_base))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def persist_scored_job(store, scored: ScoredJob) -> bool:
    """Upsert a scored posting and persist the score fields in the same call path."""
    scored.job.score = scored.score
    scored.job.tier = scored.tier
    scored.job.rationale = scored.rationale
    scored.job.resume_base = scored.resume_base
    is_new = store.upsert_job(scored.job)
    store.update_score(
        scored.job.id, scored.score, scored.tier, scored.rationale,
        resume_base=scored.resume_base,
    )
    return is_new


def sync_reviews(store) -> dict[str, int]:
    """Create pending reviews after scoring without resetting saved decisions."""
    applied = {
        application["job_id"] for application in store.applications()
        if application.get("job_id")
    }
    monitored = store.monitored_job_ids()
    cleared_before = store.meta_get(REVIEW_CLEAR_MARKER, "") or ""
    created = 0
    monitored_count = 0
    discovery_count = 0
    for job in store.jobs(order_by_score=False):
        if (job.id in applied or (job.status or "open") != "open" or
                (job.tier or "Skip") == "Skip"):
            continue
        origin = "monitored" if job.id in monitored else "discovery"
        existing = store.get_job_review(job.id)
        if (existing is None and origin == "discovery" and cleared_before
                and (not job.first_seen or job.first_seen <= cleared_before)):
            continue
        if existing is None:
            created += 1
        review = store.ensure_job_review(job.id, origins=[origin])
        if review["state"] != "pending":
            continue
        if origin == "monitored":
            monitored_count += 1
        else:
            discovery_count += 1
    return {
        "created": created,
        "pending_monitored": monitored_count,
        "pending_discovery": discovery_count,
    }


def clear_discovery_and_saved(store) -> dict[str, int | str]:
    """Clear current Discovery and Saved queues without deleting job records.

    A cutoff keeps pre-existing discovery jobs from being recreated by the next
    review sync. Newly discovered jobs and explicitly monitored jobs still enter
    review normally; dismissed decisions remain untouched.
    """
    rows = store.list_job_reviews()
    discovery_ids = [
        row["job_id"] for row in rows
        if row["state"] == "pending" and "monitored" not in row["origins"]
    ]
    saved_ids = [row["job_id"] for row in rows if row["state"] == "saved"]
    cutoff = now_iso()
    with store.conn:
        store.conn.executemany(
            "DELETE FROM job_reviews WHERE job_id = ?",
            [(job_id,) for job_id in [*discovery_ids, *saved_ids]],
        )
        store.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (REVIEW_CLEAR_MARKER, cutoff),
        )
    return {
        "discovery": len(discovery_ids),
        "saved": len(saved_ids),
        "cleared_before": cutoff,
    }