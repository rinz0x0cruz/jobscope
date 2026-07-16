"""View and update application status: funnel, follow-up reminders, and 'new'."""
from __future__ import annotations

import datetime as _dt
import html as _html
from dataclasses import dataclass
from typing import Optional

from jobscope.core.model import STATUSES, Application
from jobscope.core.store import now_iso


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


def send_digest_result(cfg: dict, store) -> DigestResult:
    """Email a digest of newly-matched Strong/Good roles since the last digest.

    Deterministic and opt-in: a no-op unless ``email.enabled``. The very first
    run only baselines the ``digest:last`` marker (so we never email the whole
    backlog at once); every run after emails just the roles first seen since the
    marker, then advances it once the send succeeds. A transient send failure
    leaves the marker untouched, so the same roles are retried next run. Reuses
    the ``email.*`` config, so it adds no new config keys. Returns the number of
    roles attempted and whether delivery completed. Disabled/baseline/no-new paths
    are successful no-ops.
    """
    if not (cfg.get("email", {}) or {}).get("enabled"):
        return DigestResult(0, True, "disabled")
    last = store.meta_get("digest:last")
    if not last:
        store.meta_set("digest:last", now_iso())   # baseline; skip the initial flood
        return DigestResult(0, True, "baseline")
    all_reviews = store.list_job_reviews()
    origins_by_job: dict[str, list[str]] = {}
    if all_reviews:
        pending = {
            review["job_id"]: review for review in all_reviews
            if review["state"] == "pending" and review["first_seen"] > last
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
        fresh = fresh[:25]
    else:
        # Pre-monitoring databases keep the historical behavior until seeded.
        fresh = [job for job in store.jobs(order_by_score=True)
                 if job.tier in ("Strong", "Good") and job.first_seen and job.first_seen > last][:25]
    if not fresh:
        return DigestResult(0, True, "no new matches")
    from jobscope.deliver import email as _email
    subject = f"jobscope: {len(fresh)} job{'s' if len(fresh) != 1 else ''} to review"
    text, html = _digest_body(fresh, origins_by_job or None)
    sent = _email.send(cfg, subject, text, html)
    if sent:
        store.meta_set("digest:last", now_iso())
    return DigestResult(
        len(fresh), sent, "sent" if sent else "SMTP delivery failed; marker retained")


def send_digest(cfg: dict, store) -> int:
    """Compatibility wrapper returning the number of roles attempted."""
    return send_digest_result(cfg, store).attempted


def _digest_body(jobs: list, origins_by_job: dict[str, list[str]] | None = None) -> tuple[str, str]:
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
