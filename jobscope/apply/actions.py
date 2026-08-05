"""Next actions: one quiet, deterministic queue of the work that can change an outcome.

Every action is derived from state jobscope already holds and carries the reason it
exists, so completing one never fabricates an application status or an email outcome.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

# Mirrors GHOST_DAYS in web/src/lib/pipeline.ts so both halves of the product agree
# on what "ghosted" means.
GHOST_DAYS = 21

# A genuine reply, as opposed to the automated "application received" confirmation.
# Mirrors RESPONSE_SIGNALS in web/src/lib/pipeline.ts.
_RESPONSE_SIGNALS = frozenset({"recruiter", "assessment", "interview", "offer", "rejection"})


@dataclass(frozen=True)
class NextAction:
    job_id: str
    reason: str
    company: str
    title: str
    age_days: int


def next_actions(cfg: dict, store) -> list[NextAction]:
    """Actions derived from current application state, most urgent first."""
    apply_cfg = cfg.get("apply", {}) or {}
    window = int(apply_cfg.get("followup_days", 7) or 0)
    ghost_after = int(apply_cfg.get("ghost_days", GHOST_DAYS) or 0)
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)

    due: list[NextAction] = []
    for application in store.applications():
        if application.get("status") != "applied":
            continue
        if _has_reply(store, application["job_id"]):
            continue
        age = _age_days(application.get("applied_at"), now)
        if age is None or age < window:
            continue
        due.append(NextAction(
            job_id=application["job_id"],
            reason="ghosted" if age >= ghost_after else "follow_up",
            company=application.get("company") or "",
            title=application.get("title") or "",
            age_days=age,
        ))
    # Company breaks ties so a shared age never falls through to comparing records.
    due.sort(key=lambda item: (-item.age_days, item.company))
    return due


def _has_reply(store, job_id: str) -> bool:
    return any(event.get("signal") in _RESPONSE_SIGNALS for event in store.mail_events(job_id))


def _age_days(applied_at: str | None, now: _dt.datetime) -> int | None:
    try:
        when = _dt.datetime.strptime((applied_at or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None
    return (now - when).days
