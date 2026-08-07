"""Next actions: one quiet, deterministic queue of the work that can change an outcome.

Every action is derived from state jobscope already holds and carries the reason it
exists, so completing one never fabricates an application status or an email outcome.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from collections.abc import Iterable
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
    due_at: _dt.date


def next_actions(cfg: dict, store) -> list[NextAction]:
    """Actions derived from current application state, most urgent first."""
    apply_cfg = cfg.get("apply", {}) or {}
    window = int(apply_cfg.get("followup_days", 7) or 0)
    ghost_after = int(apply_cfg.get("ghost_days", GHOST_DAYS) or 0)
    zone = configured_zone(cfg)
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)

    due: list[NextAction] = []
    for application in store.applications():
        if application.get("status") != "applied":
            continue
        if _has_reply(store, application["job_id"]):
            continue
        applied = _parse(application.get("applied_at"))
        if applied is None:
            continue
        age = (now - applied).days
        if age < window:
            continue
        due.append(NextAction(
            job_id=application["job_id"],
            reason="ghosted" if age >= ghost_after else "follow_up",
            company=application.get("company") or "",
            title=application.get("title") or "",
            age_days=age,
            due_at=_due_date(applied, window, zone),
        ))
    # Company breaks ties so a shared age never falls through to comparing records.
    due.sort(key=lambda item: (-item.age_days, item.company))
    return due


def configured_zone(cfg: dict):
    """The user's operating zone. Reuses the campaign resolver, which is the one place
    that already copes with a host shipping no tzdata.

    An unresolvable zone falls back to UTC rather than propagating: campaigns are right
    to refuse to send at an unknown local time, but `track` and `actions` only read, and
    losing sight of every chase over a config typo is the worse failure.
    """
    from .campaigns import _zone

    name = (((cfg.get("apply") or {}).get("campaign") or {}).get("timezone")) or "UTC"
    try:
        return _zone(name)
    except ValueError:
        return _dt.UTC


@dataclass(frozen=True)
class OutreachBlocker:
    target_id: str
    company: str
    reason: str
    age_days: int


def outreach_blockers(store, *, now: _dt.datetime | None = None) -> list[OutreachBlocker]:
    """Outreach that has stopped and will not restart on its own.

    `campaign tick` reconciles replies and reports due work; it never runs contact
    discovery, which only happens when someone asks for it. A target parked at
    needs_contact therefore waits indefinitely, and until now the only evidence was
    its absence from every other view.
    """
    current = now or _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    blocked = []
    for row in store.blocked_outreach_campaign_targets():
        created = _parse(row.get("created_at"))
        blocked.append(OutreachBlocker(
            target_id=row["id"],
            company=row.get("company") or "",
            reason=row.get("error_code") or row.get("state") or "",
            age_days=(current - created).days if created else 0,
        ))
    return blocked


def _has_reply(store, job_id: str) -> bool:
    return any(event.get("signal") in _RESPONSE_SIGNALS for event in store.mail_events(job_id))


def _parse(applied_at: str | None) -> _dt.datetime | None:
    """Stored timestamps are naive UTC; anything unparseable is not a date at all."""
    try:
        return _dt.datetime.strptime((applied_at or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None


def _due_date(applied: _dt.datetime, window: int, zone) -> _dt.date:
    """The local calendar day the chase came due. Converting the instant rather than
    the date is what keeps this right across a daylight-saving boundary."""
    due = applied.replace(tzinfo=_dt.UTC) + _dt.timedelta(days=window)
    return due.astimezone(zone).date()


_REASON_SUMMARY = {
    "follow_up": "Follow up",
    "ghosted": "Chase or close",
}

TODAY, UPCOMING, DONE, CANCELLED = "today", "upcoming", "done", "cancelled"


def bucket_of(action: dict, today: _dt.date) -> str:
    """Which view a stored action belongs in.

    An open action with no date lands in today rather than a limbo of its own: it is
    outstanding, and a queue that hides undated work is how work gets lost.
    """
    state = action.get("state") or "open"
    if state == "completed":
        return DONE
    if state == "cancelled":
        return CANCELLED
    due = as_date(action.get("due_at"))
    return UPCOMING if due is not None and due > today else TODAY


def as_date(value: str | None) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def to_ics(actions: Iterable[NextAction], *, now: _dt.datetime | None = None) -> str:
    """The dated actions as one RFC 5545 calendar.

    All-day VEVENTs rather than VTODOs: a chase is really a to-do, but the calendars
    people actually import into treat VTODO as optional, and an action you cannot see
    is worse than one filed as an event. The UID is derived from the action, so
    re-exporting updates the same entry instead of adding a second copy.
    """
    stamp = (now or _dt.datetime.now(_dt.UTC)).astimezone(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jobscope//next actions//EN",
        "CALSCALE:GREGORIAN",
    ]
    for action in actions:
        company = action.company or "unknown company"
        title = action.title or "unknown role"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_uid(action)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{action.due_at:%Y%m%d}",
            f"DTEND;VALUE=DATE:{action.due_at + _dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(f'{_REASON_SUMMARY.get(action.reason, action.reason)}: {company}')}",
            f"DESCRIPTION:{_escape(f'{title} at {company}. Applied {action.age_days} days ago with no reply. Job {action.job_id}.')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(f"{_fold(line)}\r\n" for line in lines)


def _uid(action: NextAction) -> str:
    digest = hashlib.sha256(f"{action.job_id}|{action.reason}".encode()).hexdigest()
    return f"{digest[:32]}@jobscope.local"


def _escape(value: str) -> str:
    out = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return out.replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 counts octets, not characters, so fold on real encoded width."""
    folded: list[str] = []
    current, width = "", 0
    for char in line:
        size = len(char.encode())
        if width + size > 75:
            folded.append(current)
            current, width = f" {char}", 1 + size
        else:
            current += char
            width += size
    folded.append(current)
    return "\r\n".join(folded)
