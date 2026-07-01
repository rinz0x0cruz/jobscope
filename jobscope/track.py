"""View and update application status (the pipeline tracker)."""
from __future__ import annotations

from typing import Optional

from .model import STATUSES, Application
from .store import now_iso


def run(store, set_expr: Optional[str] = None) -> int:
    if set_expr:
        return _set_status(store, set_expr)

    apps = store.applications()
    if not apps:
        print("  no applications yet. Use `prep <job_id>` to prepare one.")
        return 0
    print(f"  {len(apps)} applications:\n")
    print(f"  {'STATUS':<10} {'COMPANY':<24} {'TITLE':<34} JOB_ID")
    print("  " + "-" * 82)
    for a in apps:
        print(f"  {a['status']:<10} {(a.get('company') or '?')[:23]:<24} "
              f"{(a.get('title') or '?')[:33]:<34} {a['job_id']}")
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
