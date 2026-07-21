"""Reconcile the application funnel from the stored mail-event timeline.

Two deterministic, offline repairs:

* **reclassify** -- re-check each stored event against the *current* rules: drop
  transactional/OTP mail that slipped in, and downgrade a false ``interview`` /
  ``assessment`` tag (e.g. an acknowledgment whose body merely mentioned
    "interview") or promotional ``offer`` to its real signal. Conservative: an
    ambiguous terminal event is preserved unless retained evidence disproves it.

* **recompute** -- rebuild each application's status from its events in date
  order, *splitting* the timeline into separate application instances so one
  rejection never cuts the whole company out of the funnel. A positive event
  (application / interview / offer) that arrives after a rejection starts a NEW
  active instance (a re-application), and a distinct role gets its own instance --
  so "I re-applied" and "I applied to two roles, one was rejected" both keep an
  active row for the company instead of collapsing to a single rejected one.
"""
from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from jobscope.core.model import Application
from jobscope.core.store.base import now_iso
from jobscope.ingest import mailrules


_REQUISITION_SUBJECT = re.compile(
    r"\b(?P<id>\d{5,})\s*(?:[-\u2013\u2014:]\s*)?"
    r"[A-Za-z][A-Za-z0-9 ,+/&().-]{1,100}\s*$",
    re.I,
)
_REQUISITION_BODY = re.compile(r"\bref\s*:\s*(?P<id>\d{5,})\b", re.I)


def _norm_role(role: str) -> str:
    return (role or "").strip().lower()


def split_instances(events: list[dict]) -> list[list[dict]]:
    """Split a company's date-ordered events into separate application instances.

    Rules (walked in date order):
      * a rejection closes its instance;
      * a distinct non-empty role starts its own instance (concurrent roles);
      * an empty-role event joins the most-recent still-open instance;
      * a positive event with no open instance starts a fresh one (re-application).
    """
    instances: list[dict] = []
    for e in events:
        role = _norm_role(e.get("role"))
        target: dict | None = None
        if role:
            target = next((i for i in reversed(instances)
                           if not i["closed"] and role in i["roles"]), None)
        else:
            target = next((i for i in reversed(instances) if not i["closed"]), None)
        if target is None:
            target = {"events": [], "roles": set(), "closed": False}
            instances.append(target)
        target["events"].append(e)
        if role:
            target["roles"].add(role)
        if (e.get("signal") or "") == "rejection":
            target["closed"] = True
    return [i["events"] for i in instances]


def fold_status(events: list[dict]) -> str:
    """Coarse funnel status for one instance: fold its signals forward in date
    order (an instance is split at rejection, so this only advances)."""
    status = ""
    for e in events:
        s = mailrules.signal_to_status(e.get("signal") or "")
        if s:
            status = mailrules.advance_status(status, s)
    return status


def _first(events: list[dict], key: str) -> str:
    for e in events:
        v = (e.get(key) or "").strip()
        if v:
            return v
    return ""


def _event_identity(event: dict) -> tuple[str, str]:
    return (
        mailrules.normalize_company(event.get("company") or ""),
        _norm_role(event.get("role") or ""),
    )


def _event_requisition_ids(event: dict) -> set[str]:
    requisitions: set[str] = set()
    for text, pattern in (
        (event.get("subject") or "", _REQUISITION_SUBJECT),
        (event.get("snippet") or "", _REQUISITION_BODY),
    ):
        requisitions.update(match.group("id") for match in pattern.finditer(text))
    return requisitions


def _canonical_event_ids(store, events: list[dict]) -> dict[tuple[str, str], str]:
    canonical_jobs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for job in store.jobs(order_by_score=False):
        key = (mailrules.normalize_company(job.company), _norm_role(job.title))
        if all(key):
            canonical_jobs[key].add(job.id)

    event_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for event in events:
        key = _event_identity(event)
        if all(key):
            event_groups[key].append(event)

    canonical: dict[tuple[str, str], str] = {}
    for key, group in event_groups.items():
        job_candidates = canonical_jobs.get(key, set())
        if len(job_candidates) > 1:
            continue

        event_ids = {event.get("job_id") or "" for event in group}
        base_ids = {job_id.split("#", 1)[0] for job_id in event_ids if job_id}
        note_ids = event_ids | base_ids | job_candidates
        if any(
            (store.get_application(job_id, include_tombstoned=True) or {}).get("notes")
            for job_id in note_ids
        ):
            continue

        requisitions = {
            requisition
            for event in group
            for requisition in _event_requisition_ids(event)
        }
        if len(requisitions) > 1:
            continue

        if len(job_candidates) == 1:
            canonical[key] = next(iter(job_candidates))
            continue

        if len(requisitions) != 1:
            continue

        from .inbox import _synthetic_job_id
        stable_ids = {
            _synthetic_job_id(event.get("company") or "", event.get("role") or "")
            for event in group
        }
        existing_stable_ids = stable_ids & base_ids
        if len(existing_stable_ids) == 1:
            canonical[key] = next(iter(existing_stable_ids))
    return canonical


def recompute(store, *, initiator: str = "cli") -> dict:
    """Rebuild application status rows from the mail timeline, instance-split.

    Idempotent: events are regrouped by their BASE job id (the ``#n`` instance
    suffix is stripped first), so re-running produces the same instances.
    """
    run = store.begin_reconciliation_run("recompute", initiator)
    try:
        with store.conn:
            stats = _recompute(store, run["id"])
            store._finalize_reconciliation_run(
                run["id"], groups=stats["groups"], instances=stats["instances"],
                tombstoned=stats["tombstoned"],
            )
    except Exception:
        store.fail_reconciliation_run(run["id"], "transaction_failed")
        raise
    return {"groups": stats["groups"], "instances": stats["instances"]}


def _recompute(store, run_id: str) -> dict[str, int]:
    events = store.mail_events()
    canonical_ids = _canonical_event_ids(store, events)
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        base = (e.get("job_id") or "").split("#", 1)[0]
        if base:
            base = canonical_ids.get(_event_identity(e), base)
            groups[base].append(e)

    planned: list[tuple[str, str, str, list[dict]]] = []
    written: set[str] = set()
    for base, evs in groups.items():
        evs.sort(key=lambda e: (e.get("date") or "", e.get("first_seen") or ""))
        for idx, inst in enumerate(split_instances(evs)):
            status = fold_status(inst)
            if not status:
                continue
            jid = base if idx == 0 else f"{base}#{idx + 1}"
            planned.append((jid, base, status, inst))
            written.add(base)

    desired_ids = {jid for jid, _base, _status, _inst in planned}
    tombstoned = 0
    # Only stale instance rows absent from the new plan are tombstoned. Planned
    # instance IDs remain in place, so an idempotent recompute performs no churn.
    for a in store.applications():
        jid = a.get("job_id") or ""
        if ("#" in jid and jid not in desired_ids and
                not bool(a.get("reconciliation_exempt"))):
            if store._tombstone_application(
                    jid, reason="stale_instance_replaced", run_id=run_id):
                store._append_reconciliation_decision(
                    run_id, decision_type="application_tombstoned",
                    application_id=jid, base_job_id=jid.split("#", 1)[0],
                    old_status=a.get("status") or "",
                    reason_code="stale_instance_replaced", recoverable=True,
                )
                tombstoned += 1

    for jid, base, status, inst in planned:
        for event in inst:
            if (event.get("job_id") or "") != jid:
                store._update_mail_event(event["id"], job_id=jid)
                store._append_reconciliation_decision(
                    run_id, decision_type="instance_relinked",
                    application_id=jid, base_job_id=base,
                    reason_code="instance_assignment_changed",
                )
        _write_status(store, jid, base, status, inst, run_id)

    # Tombstone orphaned synthetic mail apps whose events no longer carry funnel
    # evidence. Also heal stale inbox-derived offers when older company-only
    # linking reused a scraped job id; do not rewrite other scraped-id statuses.
    for a in store.applications():
        jid = a.get("job_id") or ""
        base = jid.split("#", 1)[0]
        stale_inbox_offer = (
            a.get("source") in {"inbox", "email"} and a.get("status") == "offer"
        )
        email_derived = base.startswith("mail:") or stale_inbox_offer
        if (email_derived and base not in written and
                not bool(a.get("reconciliation_exempt"))):
            if store._tombstone_application(
                    jid, reason="orphan_mail_application", run_id=run_id):
                store._append_reconciliation_decision(
                    run_id, decision_type="application_tombstoned",
                    application_id=jid, base_job_id=base,
                    old_status=a.get("status") or "",
                    reason_code="orphan_mail_application", recoverable=True,
                )
                tombstoned += 1
    return {
        "groups": len(groups), "instances": len(planned), "tombstoned": tombstoned,
    }


def _write_status(store, jid: str, base: str, status: str, inst: list[dict],
                  run_id: str) -> None:
    existing = store.get_application(jid, include_tombstoned=True) or {}
    was_tombstoned = bool(existing.get("tombstoned_at"))
    old_status = existing.get("status") or ""
    applied_at = existing.get("applied_at") or ""
    if status in ("applied", "interview", "offer") and not applied_at:
        applied_at = _first(inst, "date") or now_iso()
    # Email-derived ("mail:") apps take their company/role from the (re-parsed)
    # events, so a healed name propagates; a scraped-job app keeps its authoritative
    # scraped company and only backfills from events when it has none.
    ev_company, ev_role = _first(inst, "company"), _first(inst, "role")
    if base.startswith("mail:"):
        company = ev_company or existing.get("company", "")
        title = ev_role or existing.get("title", "")
    else:
        company = existing.get("company") or ev_company
        title = existing.get("title") or ev_role
    store._set_application(Application(
        job_id=jid,
        status=status,
        package_dir=existing.get("package_dir", ""),
        resume_path=existing.get("resume_path", ""),
        cover_path=existing.get("cover_path", ""),
        applied_at=applied_at,
        notes=existing.get("notes", ""),
        company=company,
        title=title,
        source=existing.get("source", "") or "email",
        updated=now_iso(),
    ), clear_tombstone=was_tombstoned, reconciliation_run_id=run_id)
    if not existing:
        store._append_reconciliation_decision(
            run_id, decision_type="instance_rebuilt",
            application_id=jid, base_job_id=base, new_status=status,
            reason_code="rebuilt_instance_active",
        )
    elif was_tombstoned:
        store._append_reconciliation_decision(
            run_id, decision_type="tombstone_cleared",
            application_id=jid, base_job_id=base, old_status=old_status,
            new_status=status, reason_code="rebuilt_instance_active",
        )
    elif old_status != status:
        store._append_reconciliation_decision(
            run_id, decision_type="status_changed",
            application_id=jid, base_job_id=base, old_status=old_status,
            new_status=status, reason_code="status_fold_changed",
        )


def _reclassification(ev: dict) -> tuple[str | None, str]:
    """Return the new signal and its controlled audit reason.

    Conservative repair: drop OTP/verification mail and content/practice-platform
    newsletters (LeetCode contests, course "challenges", ...), and downgrade a
    false ``interview`` / ``assessment`` / ``offer`` tag to whatever the current
    rules say. Terminal events are only reconsidered when their body evidence was
    retained; otherwise reconciliation stays conservative.
    """
    subject = ev.get("subject") or ""
    snippet = ev.get("snippet") or ""
    if mailrules.is_transactional(subject, snippet):
        return None, "transactional_event"
    if mailrules.is_newsletter_domain(ev.get("from_domain") or ""):
        return None, "newsletter_event"
    sig = ev.get("signal") or ""
    if sig in ("interview", "assessment", "offer"):
        new = mailrules.classify_scored(subject, snippet)[0]
        # Downgrade to a CLEAR acknowledgment/terminal whenever the re-score says so.
        if new in ("confirmation", "rejection"):
            return new, "classification_rule_changed"
        # A re-score to "other" is only trusted when we still have the body (a stored
        # snippet): then a JD-phrase false assessment ("...gap assessments role") or a
        # bare-mention interview is confidently demoted out of the funnel. Without a
        # snippet we stay conservative -- a real interview whose cue lived in a body we
        # no longer store must never be silently dropped.
        if new == "other" and (snippet or "").strip():
            return "other", "classification_rule_changed"
        if (sig == "offer" and new == "other"
                and mailrules.is_non_employment_offer(subject, snippet)):
            return "other", "classification_rule_changed"
    return sig, ""


def reclassify_signal(ev: dict) -> str | None:
    """New signal for a stored event, or None if it should be dropped."""
    return _reclassification(ev)[0]


def reclassify(store, *, initiator: str = "cli") -> dict:
    """Re-check every stored event, drop transactional mail, then recompute."""
    run = store.begin_reconciliation_run("reclassify", initiator)
    try:
        with store.conn:
            stats = _reclassify(store, run["id"])
            store._finalize_reconciliation_run(
                run["id"], groups=stats["groups"], instances=stats["instances"],
                reclassified=stats["reclassified"], dropped=stats["dropped"],
                tombstoned=stats["tombstoned"],
            )
    except Exception:
        store.fail_reconciliation_run(run["id"], "transaction_failed")
        raise
    return {
        "groups": stats["groups"], "instances": stats["instances"],
        "reclassified": stats["reclassified"], "dropped": stats["dropped"],
    }


def _reclassify(store, run_id: str) -> dict[str, int]:
    dropped = changed = 0
    for ev in store.mail_events():
        new, reason = _reclassification(ev)
        application_id = ev.get("job_id") or ""
        base_job_id = application_id.split("#", 1)[0]
        if new is None:
            store._delete_mail_event(ev["id"])
            store._append_reconciliation_decision(
                run_id, decision_type="event_dropped",
                application_id=application_id, base_job_id=base_job_id,
                old_signal=ev.get("signal") or "", reason_code=reason,
            )
            dropped += 1
            continue
        updates: dict[str, str] = {}
        if new != (ev.get("signal") or ""):
            updates["signal"] = new
        # Re-parse company/role from the stored headers so names that older rules
        # mangled ("IBM Talent Acquisition" -> "IBM Acquisition"; a subject glued in
        # as the company) heal in place on the next pass.
        co, ro = mailrules.parse_company_role(
            ev.get("from_name") or "", ev.get("from_domain") or "",
            ev.get("subject") or "", ev.get("snippet") or "")
        if co and co != (ev.get("company") or ""):
            updates["company"] = co
        if ro and ro != (ev.get("role") or ""):
            updates["role"] = ro
        if updates:
            store._update_mail_event(ev["id"], **updates)
            if "signal" in updates:
                store._append_reconciliation_decision(
                    run_id, decision_type="signal_reclassified",
                    application_id=application_id, base_job_id=base_job_id,
                    old_signal=ev.get("signal") or "", new_signal=updates["signal"],
                    reason_code=reason,
                )
                changed += 1
            if "company" in updates:
                store._append_reconciliation_decision(
                    run_id, decision_type="company_reparsed",
                    application_id=application_id, base_job_id=base_job_id,
                    reason_code="parsed_company_changed",
                )
            if "role" in updates:
                store._append_reconciliation_decision(
                    run_id, decision_type="role_reparsed",
                    application_id=application_id, base_job_id=base_job_id,
                    reason_code="parsed_role_changed",
                )
    stats: dict[str, Any] = _recompute(store, run_id)
    stats.update(reclassified=changed, dropped=dropped)
    return stats
