"""Explicit, audited recovery of reconciliation-tombstoned applications."""
from __future__ import annotations

from typing import Any

from jobscope.core.store.reconciliation_audit import APPLICATION_STATUSES


def _restore_application_in_run(store, job_id: str, run_id: str) -> dict[str, Any]:
    """Restore one application inside the caller's transaction and audit run."""
    application = store.get_application(job_id, include_tombstoned=True)
    if application is None or not application.get("tombstoned_at"):
        return {"ok": True, "restored": False, "run_id": ""}
    restored = store._restore_application(job_id, run_id=run_id)
    if restored:
        status = application.get("status") or ""
        store._append_reconciliation_decision(
            run_id, decision_type="application_restored",
            application_id=job_id, base_job_id=job_id.split("#", 1)[0],
            new_status=status if status in APPLICATION_STATUSES else "",
            reason_code="recovery_requested",
        )
    return {"ok": True, "restored": restored, "run_id": run_id if restored else ""}


def restore_application(store, job_id: str, *, initiator: str = "user") -> dict[str, Any]:
    """Restore one tombstone and exempt it from automatic reconciliation removal."""
    application = store.get_application(job_id, include_tombstoned=True)
    if application is None or not application.get("tombstoned_at"):
        return {"ok": True, "restored": False, "run_id": ""}

    run = store.begin_reconciliation_run("restore", initiator)
    try:
        with store.conn:
            result = _restore_application_in_run(store, job_id, run["id"])
            store._finalize_reconciliation_run(
                run["id"], restored=int(result["restored"]),
            )
    except Exception:
        store.fail_reconciliation_run(run["id"], "transaction_failed")
        raise
    return result