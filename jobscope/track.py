"""View and update application status: funnel, follow-up reminders, and 'new'."""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from .model import STATUSES, Application
from .store import now_iso


def run(store, set_expr: Optional[str] = None, cfg: Optional[dict] = None) -> int:
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
