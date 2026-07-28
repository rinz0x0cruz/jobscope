"""View and update application status: funnel, follow-up reminders, and 'new'."""
from __future__ import annotations

import datetime as _dt
import hashlib
import html as _html
import json
from dataclasses import dataclass
from typing import Optional

from jobscope.core.model import STATUSES, Application
from jobscope.core.store import now_iso

_DIGEST_INTENT_KEY = "digest:intent:v1"
_DIGEST_STALE_AFTER = _dt.timedelta(minutes=15)
_DIGEST_MAX_ROWS = 25


@dataclass(frozen=True, slots=True)
class DigestResult:
    attempted: int
    sent: bool
    detail: str = ""


def run(store, set_expr: Optional[str] = None, cfg: Optional[dict] = None,
        timeline: Optional[str] = None) -> int:
    if timeline:
        return _print_timeline(store, timeline)
    if set_expr:
        return _set_status(store, set_expr)

    apps = store.applications()
    if not apps:
        print("  no applications yet. Use `prep <job_id>` to prepare one.")
        return 0

    _print_funnel(apps)
    print(f"\n  {len(apps)} applications:\n")
    print(f"  {'STATUS':<10} {'COMPANY':<24} {'TITLE':<34} JOB_ID")
    print("  " + "-" * 82)
    for a in apps:
        print(f"  {a['status']:<10} {(a.get('company') or '?')[:23]:<24} "
              f"{(a.get('title') or '?')[:33]:<34} {a['job_id']}")

    _print_reminders(apps, (cfg or {}).get("apply", {}).get("followup_days", 7))
    return 0


def _print_funnel(apps: list) -> None:
    counts: dict[str, int] = {}
    for a in apps:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    order = ["new", "prepared", "applied", "interview", "offer", "rejected", "skipped"]
    strip = "  ".join(f"{s}:{counts[s]}" for s in order if counts.get(s))
    applied = counts.get("applied", 0) + counts.get("interview", 0) + \
        counts.get("offer", 0) + counts.get("rejected", 0)
    interviews = counts.get("interview", 0) + counts.get("offer", 0)
    offers = counts.get("offer", 0)
    print(f"  funnel: {strip}")
    if applied:
        resp = interviews + counts.get("rejected", 0)
        print(f"  rates:  response {_pct(resp, applied)}  "
              f"interview {_pct(interviews, applied)}  offer {_pct(offers, applied)}  "
              f"(base: {applied} submitted)")


def _print_reminders(apps: list, followup_days: int) -> None:
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    due = []
    for a in apps:
        if a["status"] != "applied" or not a.get("applied_at"):
            continue
        try:
            when = _dt.datetime.strptime(a["applied_at"][:19], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            continue
        age = (now - when).days
        if age >= followup_days:
            due.append((age, a))
    if due:
        print(f"\n  Follow-up due ({len(due)}, applied >= {followup_days}d ago, no reply):")
        for age, a in sorted(due, reverse=True):
            print(f"    - {(a.get('company') or '?')} / {(a.get('title') or '?')[:40]} "
                  f"({age}d) [{a['job_id']}]")


def run_new(store) -> int:
    """Show jobs first seen since your last review, then advance the marker."""
    last = store.meta_get("last_review")
    ranked = store.jobs(order_by_score=True)
    fresh = [j for j in ranked if j.tier in ("Strong", "Good")
             and (not last or (j.first_seen and j.first_seen > last))]
    if not fresh:
        print("  no new Strong/Good jobs since your last review.")
    else:
        print(f"  {len(fresh)} new Strong/Good jobs since last review:\n")
        print(f"  {'SCORE':>5} {'TIER':<7} {'COMPANY':<22} TITLE")
        print("  " + "-" * 74)
        for j in fresh:
            print(f"  {j.score:>5} {j.tier:<7} {(j.company or '?')[:21]:<22} {j.title[:34]}")
    store.meta_set("last_review", now_iso())
    return 0


def send_digest_result(cfg: dict, store, *, retry_intent: bool = False) -> DigestResult:
    """Email a digest of newly-matched Strong/Good roles since the last digest.

    The selected content and Message-ID are persisted before SMTP. Known
    pre-send/rejection failures may be explicitly retried with that same ID;
    interrupted or ambiguous attempts remain blocked until Sent reconciliation.
    """
    if not (cfg.get("email", {}) or {}).get("enabled"):
        return DigestResult(0, True, "disabled")
    raw_intent = store.meta_get(_DIGEST_INTENT_KEY)
    if raw_intent:
        try:
            intent = _decode_digest_intent(raw_intent)
        except ValueError:
            return DigestResult(0, False, "invalid durable digest intent; SMTP blocked")
        if intent["state"] == "accepted":
            finalized = _finalize_digest_acceptance(store, raw_intent, intent)
            return DigestResult(
                len(intent["job_ids"]), finalized,
                "accepted digest finalized" if finalized
                else "accepted digest state could not be finalized",
            )
        elif intent["state"] == "sending":
            if _digest_attempt_stale(intent):
                unknown = {**intent, "state": "delivery_unknown"}
                unknown_raw = _encode_digest_intent(unknown)
                store.meta_compare_and_set(_DIGEST_INTENT_KEY, raw_intent, unknown_raw)
            return DigestResult(
                len(intent["job_ids"]), False,
                "digest delivery outcome unresolved; reconcile Sent mail before retry",
            )
        elif intent["state"] == "delivery_unknown":
            return DigestResult(
                len(intent["job_ids"]), False,
                "digest delivery outcome unresolved; reconcile Sent mail before retry",
            )
        elif intent["state"] == "retryable" and not retry_intent:
            return DigestResult(
                len(intent["job_ids"]), False,
                "digest retry requires an explicit `new --email` command",
            )
    else:
        intent = None

    last = store.meta_get("digest:last")
    if intent is None and not last:
        store.meta_set("digest:last", now_iso())   # baseline; skip the initial flood
        return DigestResult(0, True, "baseline")
    if intent is None:
        cutoff = now_iso()
        fresh, origins_by_job, remaining = _fresh_digest_jobs(store, last, cutoff)
        if not fresh:
            return DigestResult(0, True, "no new matches")
        subject = f"jobscope: {len(fresh)} job{'s' if len(fresh) != 1 else ''} to review"
        text, html = _digest_body(fresh, origins_by_job or None, remaining=remaining)
        intent = {
            "version": 1,
            "state": "ready",
            "marker": last,
            "next_marker": cutoff,
            "job_ids": [job.id for job in fresh],
            "message_id": _digest_message_id(cfg, last, [job.id for job in fresh]),
            "subject": subject,
            "text": text,
            "html": html,
            "created_at": cutoff,
            "attempted_at": "",
            "last_outcome": "",
        }
        raw_intent = _encode_digest_intent(intent)
        if not store.meta_compare_and_set(_DIGEST_INTENT_KEY, None, raw_intent):
            return DigestResult(
                len(fresh), False, "another digest operation created the durable intent",
            )

    sending = {
        **intent,
        "state": "sending",
        "attempted_at": now_iso(),
        "last_outcome": "",
    }
    sending_raw = _encode_digest_intent(sending)
    if not store.meta_compare_and_set(_DIGEST_INTENT_KEY, raw_intent, sending_raw):
        return DigestResult(
            len(intent["job_ids"]), False, "another digest operation claimed delivery",
        )

    from jobscope.deliver import email as _email
    try:
        sent = _email.send(
            cfg, intent["subject"], intent["text"], intent["html"],
            message_id=intent["message_id"], raise_errors=True,
        )
    except _email.EmailDeliveryError as exc:
        state = "delivery_unknown" if exc.outcome_unknown else "retryable"
        failed = {**sending, "state": state, "last_outcome": exc.outcome}
        store.meta_compare_and_set(
            _DIGEST_INTENT_KEY, sending_raw, _encode_digest_intent(failed),
        )
        detail = (
            "delivery outcome unknown; reconcile Sent mail before retry"
            if exc.outcome_unknown else f"SMTP {exc.outcome}; intent retained for explicit retry"
        )
        return DigestResult(len(intent["job_ids"]), False, detail)
    if not sent:
        retryable = {**sending, "state": "retryable", "last_outcome": "pre_send_failure"}
        store.meta_compare_and_set(
            _DIGEST_INTENT_KEY, sending_raw, _encode_digest_intent(retryable),
        )
        return DigestResult(
            len(intent["job_ids"]), False,
            "SMTP pre-send failure; intent retained for explicit retry",
        )

    accepted = {**sending, "state": "accepted", "last_outcome": "accepted"}
    accepted_raw = _encode_digest_intent(accepted)
    if not store.meta_compare_and_set(_DIGEST_INTENT_KEY, sending_raw, accepted_raw):
        return DigestResult(
            len(intent["job_ids"]), False,
            "submission accepted but durable state conflicted; retry blocked",
        )
    if not _finalize_digest_acceptance(store, accepted_raw, accepted):
        return DigestResult(
            len(intent["job_ids"]), False,
            "submission accepted but durable finalization conflicted; retry blocked",
        )
    return DigestResult(
        len(intent["job_ids"]), True, "accepted by submission MTA")


def _fresh_digest_jobs(store, last: str, cutoff: str) -> tuple[list, dict[str, list[str]], int]:
    all_reviews = store.list_job_reviews()
    origins_by_job: dict[str, list[str]] = {}
    if all_reviews:
        pending = {
            review["job_id"]: review for review in all_reviews
            if review["state"] == "pending" and last < review["first_seen"] <= cutoff
        }
        fresh = [
            job for job in store.jobs(order_by_score=True)
            if job.id in pending and job.tier in ("Strong", "Good")
        ]
        origins_by_job = {job_id: review["origins"] for job_id, review in pending.items()}
        fresh.sort(key=lambda job: (
            0 if "monitored" in origins_by_job.get(job.id, []) else 1,
            -float(job.score or 0),
        ))
        return fresh[:_DIGEST_MAX_ROWS], origins_by_job, max(0, len(fresh) - _DIGEST_MAX_ROWS)
    fresh = [
        job for job in store.jobs(order_by_score=True)
        if job.tier in ("Strong", "Good") and job.first_seen
        and last < job.first_seen <= cutoff
    ]
    return fresh[:_DIGEST_MAX_ROWS], origins_by_job, max(0, len(fresh) - _DIGEST_MAX_ROWS)


def _digest_message_id(cfg: dict, marker: str, job_ids: list[str]) -> str:
    sender = str((cfg.get("email", {}) or {}).get("from_addr") or "")
    domain = sender.rsplit("@", 1)[-1].lower() if "@" in sender else "localhost"
    basis = marker + "\0" + "\0".join(sorted(job_ids))
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
    return f"jobscope-digest-{digest}@{domain}"


def _encode_digest_intent(intent: dict) -> str:
    return json.dumps(intent, sort_keys=True, separators=(",", ":"))


def _decode_digest_intent(raw: str) -> dict:
    try:
        intent = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid digest intent") from exc
    required = {
        "version", "state", "marker", "next_marker", "job_ids", "message_id",
        "subject", "text", "html", "created_at", "attempted_at", "last_outcome",
    }
    states = {"ready", "retryable", "sending", "delivery_unknown", "accepted"}
    if (
        not isinstance(intent, dict)
        or set(intent) != required
        or intent.get("version") != 1
        or intent.get("state") not in states
        or not isinstance(intent.get("job_ids"), list)
        or not intent.get("job_ids")
        or any(not isinstance(value, str) or not value for value in intent["job_ids"])
        or any(not isinstance(intent.get(key), str) for key in required - {"version", "job_ids"})
        or not intent.get("message_id")
    ):
        raise ValueError("invalid digest intent")
    return intent


def _digest_attempt_stale(intent: dict) -> bool:
    try:
        attempted = _dt.datetime.fromisoformat(intent["attempted_at"].replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return True
    return _dt.datetime.now(_dt.UTC) - attempted >= _DIGEST_STALE_AFTER


def _finalize_digest_acceptance(store, raw_intent: str, intent: dict) -> bool:
    return store.meta_finalize_intent(
        _DIGEST_INTENT_KEY, raw_intent, "digest:last", intent["next_marker"],
    )


def send_digest(cfg: dict, store) -> int:
    """Compatibility wrapper returning the number of roles attempted."""
    return send_digest_result(cfg, store, retry_intent=True).attempted


def reconcile_digest_delivery(cfg: dict, store) -> dict:
    """Resolve one ambiguous digest attempt by exact read-only Sent lookup."""
    raw_intent = store.meta_get(_DIGEST_INTENT_KEY)
    if not raw_intent:
        return {"ok": False, "code": "no_unresolved_digest"}
    try:
        intent = _decode_digest_intent(raw_intent)
    except ValueError:
        return {"ok": False, "code": "invalid_digest_intent"}
    if intent["state"] == "sending":
        if not _digest_attempt_stale(intent):
            return {"ok": False, "code": "digest_send_in_progress"}
        unknown = {**intent, "state": "delivery_unknown"}
        unknown_raw = _encode_digest_intent(unknown)
        if not store.meta_compare_and_set(_DIGEST_INTENT_KEY, raw_intent, unknown_raw):
            return {"ok": False, "code": "digest_state_conflict"}
        intent, raw_intent = unknown, unknown_raw
    if intent["state"] != "delivery_unknown":
        return {"ok": False, "code": "no_unresolved_digest"}

    from jobscope.ingest import inbox
    evidence = inbox.find_sent_message(cfg, intent["message_id"])
    if not evidence.get("ok"):
        return {
            "ok": False, "code": evidence.get("code") or "sent_reconciliation_failed",
            "message_id": intent["message_id"],
        }
    status = str(evidence.get("status") or "")
    count = int(evidence.get("count") or 0)
    if status == "multiple":
        return {
            "ok": False, "code": "multiple_sent_matches", "status": status,
            "count": count, "message_id": intent["message_id"],
        }
    if status == "sent":
        accepted = {**intent, "state": "accepted", "last_outcome": "accepted"}
        accepted_raw = _encode_digest_intent(accepted)
        if not store.meta_compare_and_set(
            _DIGEST_INTENT_KEY, raw_intent, accepted_raw,
        ):
            return {"ok": False, "code": "digest_state_conflict"}
        if not _finalize_digest_acceptance(store, accepted_raw, accepted):
            return {"ok": False, "code": "digest_state_conflict"}
    elif status == "not_found":
        retryable = {
            **intent, "state": "retryable", "last_outcome": "not_found_in_sent",
        }
        if not store.meta_compare_and_set(
            _DIGEST_INTENT_KEY, raw_intent, _encode_digest_intent(retryable),
        ):
            return {"ok": False, "code": "digest_state_conflict"}
    else:
        return {"ok": False, "code": "invalid_sent_evidence"}
    return {
        "ok": True, "code": status, "status": status, "count": count,
        "message_id": intent["message_id"],
    }


def _digest_body(jobs: list, origins_by_job: dict[str, list[str]] | None = None,
                 *, remaining: int = 0) -> tuple[str, str]:
    """Render the (plain-text, HTML) bodies for the new-match digest."""
    groups: list[tuple[str, list]]
    if origins_by_job:
        monitored = [job for job in jobs if "monitored" in origins_by_job.get(job.id, [])]
        discovery = [job for job in jobs if job not in monitored]
        groups = [("Monitored companies", monitored), ("Discovery", discovery)]
    else:
        groups = [("Matches", jobs)]

    text_parts = ["Jobs ready for review:"]
    html_parts = ["<p>Jobs ready for review:</p>"]
    for label, group in groups:
        if not group:
            continue
        lines, rows = [], []
        for job in group:
            company = job.company or "?"
            title = job.title or "?"
            location = "Remote" if job.is_remote else (job.location or "")
            lines.append(f"  [{job.tier}] {company} — {title} ({int(job.score)})"
                         + (f"  {location}" if location else ""))
            cell = _html.escape(title)
            title_html = (f'<a href="{_html.escape(job.url, quote=True)}">{cell}</a>'
                          if job.url else cell)
            rows.append(
                f"<tr><td>{_html.escape(job.tier or '')}</td>"
                f"<td>{_html.escape(company)}</td><td>{title_html}</td>"
                f"<td align='right'>{int(job.score)}</td>"
                f"<td>{_html.escape(location)}</td></tr>"
            )
        text_parts.extend(["", f"{label} ({len(group)}):", *lines])
        html_parts.extend([
            f"<h3>{_html.escape(label)} ({len(group)})</h3>",
            "<table cellpadding='6' style='border-collapse:collapse'>",
            "<tr><th align='left'>Tier</th><th align='left'>Company</th>"
            "<th align='left'>Role</th><th align='right'>Score</th>"
            "<th align='left'>Location</th></tr>",
            *rows,
            "</table>",
        ])
    if remaining > 0:
        note = f"{remaining} more new match(es) remain in your review queue."
        text_parts.extend(["", note])
        html_parts.append(f"<p>{_html.escape(note)}</p>")
    return "\n".join(text_parts) + "\n", "".join(html_parts)


def _set_status(store, expr: str) -> int:
    if "=" not in expr:
        print("  use --set job_id=status  (e.g. --set 1a2b3c=applied)")
        return 1
    job_id, _, status = expr.partition("=")
    job_id, status = job_id.strip(), status.strip().lower()
    if status not in STATUSES:
        print(f"  unknown status '{status}'. valid: {', '.join(STATUSES)}")
        return 1
    existing = {a["job_id"]: a for a in store.applications()}.get(job_id)
    app = Application(
        job_id=job_id,
        status=status,
        package_dir=(existing or {}).get("package_dir", ""),
        resume_path=(existing or {}).get("resume_path", ""),
        cover_path=(existing or {}).get("cover_path", ""),
        applied_at=now_iso() if status == "applied" else (existing or {}).get("applied_at", ""),
        notes=(existing or {}).get("notes", ""),
    )
    store.set_application(app)
    print(f"  {job_id} -> {status}")
    return 0


def _pct(n: int, d: int) -> str:
    return f"{(100 * n / d):.0f}%" if d else "n/a"


def _print_timeline(store, job_id: str) -> int:
    """Show the email history (mail_events) behind one application's status."""
    events = store.mail_events(job_id)
    if not events:
        print(f"  no email events for {job_id}. Run `python -m jobscope inbox` first.")
        return 0
    app = store.get_application(job_id) or {}
    label = app.get("company") or events[0].get("company") or "?"
    print(f"  timeline for {label} [{job_id}] -- {len(events)} email(s):\n")
    print(f"  {'DATE':<12} {'SIGNAL':<12} SUBJECT")
    print("  " + "-" * 74)
    for e in events:
        print(f"  {(e.get('date') or '')[:10]:<12} {(e.get('signal') or ''):<12} "
              f"{(e.get('subject') or '')[:46]}")
    return 0
