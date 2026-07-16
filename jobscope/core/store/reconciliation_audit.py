"""Privacy-bounded reconciliation runs, decisions, tombstones, and recovery."""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from ..model import SIGNALS, STATUSES
from .base import now_iso

AUDIT_SCHEMA_VERSION = 1

RUN_ACTIONS = frozenset({"recompute", "reclassify", "restore"})
RUN_INITIATORS = frozenset({"cli", "local_refresh", "cloud_refresh", "user"})
DECISION_TYPES = frozenset({
    "signal_reclassified",
    "event_dropped",
    "company_reparsed",
    "role_reparsed",
    "instance_relinked",
    "instance_rebuilt",
    "status_changed",
    "application_tombstoned",
    "application_restored",
    "tombstone_cleared",
})
REASON_CODES = frozenset({
    "transactional_event",
    "newsletter_event",
    "classification_rule_changed",
    "parsed_company_changed",
    "parsed_role_changed",
    "instance_assignment_changed",
    "status_fold_changed",
    "stale_instance_replaced",
    "orphan_mail_application",
    "rebuilt_instance_active",
    "recovery_requested",
})
APPLICATION_STATUSES = frozenset([*STATUSES, "withdrawn", "closed"])
MAIL_SIGNALS = frozenset(SIGNALS)
FAILURE_CODES = frozenset({
    "transaction_failed", "validation_failed", "unexpected_error",
})
_ID_RE = re.compile(r"^[A-Za-z0-9:._#-]{0,240}$")


def _controlled(value: str, allowed: frozenset[str], label: str,
                *, empty: bool = False) -> str:
    cleaned = (value or "").strip()
    if empty and not cleaned:
        return ""
    if cleaned not in allowed:
        raise ValueError(f"unsupported {label}: {cleaned!r}")
    return cleaned


def _identifier(value: str, label: str) -> str:
    cleaned = (value or "").strip()
    if not _ID_RE.fullmatch(cleaned):
        raise ValueError(f"invalid {label}")
    return cleaned


def _run_dict(row) -> dict[str, Any]:
    result = dict(row)
    result["baseline_only"] = bool(result.get("baseline_only"))
    return result


def _decision_dict(row) -> dict[str, Any]:
    result = dict(row)
    result["recoverable"] = bool(result.get("recoverable"))
    return result


class ReconciliationAuditMixin:
    def _active_application_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM applications "
            "WHERE COALESCE(tombstoned_at, '') = ''"
        ).fetchone()
        return int(row["count"])

    def _mail_event_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM mail_events").fetchone()
        return int(row["count"])

    def begin_reconciliation_run(self, action: str, initiator: str, *,
                                 applications_before: int | None = None,
                                 events_before: int | None = None,
                                 baseline_only: bool = False) -> dict[str, Any]:
        action = _controlled(action, RUN_ACTIONS, "audit action")
        initiator = _controlled(initiator, RUN_INITIATORS, "audit initiator")
        run_id = f"reconcile:{uuid.uuid4().hex}"
        self.conn.execute(
            "INSERT INTO reconciliation_runs (id, action, initiator, started_at, "
            "applications_before, events_before, schema_version, baseline_only) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, action, initiator, now_iso(),
                self._active_application_count()
                if applications_before is None else int(applications_before),
                self._mail_event_count() if events_before is None else int(events_before),
                AUDIT_SCHEMA_VERSION, int(bool(baseline_only)),
            ),
        )
        self.conn.commit()
        return self.get_reconciliation_run(run_id)

    def get_reconciliation_run(self, run_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM reconciliation_runs WHERE id = ?", (run_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown reconciliation run: {run_id}")
        return _run_dict(row)

    def _finalize_reconciliation_run(self, run_id: str, *,
                                     applications_after: int | None = None,
                                     events_after: int | None = None,
                                     groups: int = 0, instances: int = 0,
                                     reclassified: int = 0, dropped: int = 0,
                                     tombstoned: int = 0, restored: int = 0) -> None:
        self.get_reconciliation_run(run_id)
        self.conn.execute(
            "UPDATE reconciliation_runs SET status = 'completed', completed_at = ?, "
            "applications_after = ?, events_after = ?, groups_count = ?, "
            "instances_count = ?, reclassified_count = ?, dropped_count = ?, "
            "tombstoned_count = ?, restored_count = ?, error_code = '' WHERE id = ?",
            (
                now_iso(),
                self._active_application_count()
                if applications_after is None else int(applications_after),
                self._mail_event_count() if events_after is None else int(events_after),
                int(groups), int(instances), int(reclassified), int(dropped),
                int(tombstoned), int(restored), run_id,
            ),
        )

    def finalize_reconciliation_run(self, run_id: str, **counts: Any) -> dict[str, Any]:
        self._finalize_reconciliation_run(run_id, **counts)
        self.conn.commit()
        return self.get_reconciliation_run(run_id)

    def fail_reconciliation_run(self, run_id: str,
                                error_code: str = "transaction_failed") -> dict[str, Any]:
        error_code = _controlled(error_code, FAILURE_CODES, "error code")
        self.get_reconciliation_run(run_id)
        self.conn.execute(
            "UPDATE reconciliation_runs SET status = 'failed', completed_at = ?, "
            "error_code = ? WHERE id = ?",
            (now_iso(), error_code, run_id),
        )
        self.conn.commit()
        return self.get_reconciliation_run(run_id)

    def _append_reconciliation_decision(self, run_id: str, *, decision_type: str,
                                        reason_code: str, base_job_id: str = "",
                                        application_id: str = "", old_status: str = "",
                                        new_status: str = "", old_signal: str = "",
                                        new_signal: str = "", recoverable: bool = False,
                                        ) -> dict[str, Any]:
        decision_type = _controlled(decision_type, DECISION_TYPES, "decision type")
        reason_code = _controlled(reason_code, REASON_CODES, "reason code")
        old_status = _controlled(old_status, APPLICATION_STATUSES, "old status", empty=True)
        new_status = _controlled(new_status, APPLICATION_STATUSES, "new status", empty=True)
        old_signal = _controlled(old_signal, MAIL_SIGNALS, "old signal", empty=True)
        new_signal = _controlled(new_signal, MAIL_SIGNALS, "new signal", empty=True)
        run = self.get_reconciliation_run(run_id)
        if run["status"] != "running":
            raise ValueError("reconciliation run is not running")
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence "
            "FROM reconciliation_decisions WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        sequence = int(row["next_sequence"])
        decision_id = f"{run_id}:{sequence:06d}"
        self.conn.execute(
            "INSERT INTO reconciliation_decisions (id, run_id, sequence, base_job_id, "
            "application_id, decision_type, old_status, new_status, old_signal, "
            "new_signal, reason_code, recoverable, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                decision_id, run_id, sequence, _identifier(base_job_id, "base job id"),
                _identifier(application_id, "application id"), decision_type,
                old_status, new_status, old_signal, new_signal, reason_code,
                int(bool(recoverable)), now_iso(),
            ),
        )
        row = self.conn.execute(
            "SELECT * FROM reconciliation_decisions WHERE id = ?", (decision_id,),
        ).fetchone()
        return _decision_dict(row)

    def append_reconciliation_decision(self, run_id: str, **decision: Any) -> dict[str, Any]:
        result = self._append_reconciliation_decision(run_id, **decision)
        self.conn.commit()
        return result

    def reconciliation_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM reconciliation_runs ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        )
        return [_run_dict(row) for row in rows]

    def reconciliation_decisions(self, run_id: str,
                                 limit: int = 500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM reconciliation_decisions WHERE run_id = ? "
            "ORDER BY sequence LIMIT ?",
            (run_id, max(1, min(int(limit), 1000))),
        )
        return [_decision_dict(row) for row in rows]

    def reconciliation_summary(self, run_id: str) -> dict[str, Any]:
        run = self.get_reconciliation_run(run_id)
        before = int(run["applications_before"] or 0)
        after = run["applications_after"]
        event_before = int(run["events_before"] or 0)
        event_after = run["events_after"]
        return {
            **run,
            "application_delta": None if after is None else int(after) - before,
            "event_delta": None if event_after is None else int(event_after) - event_before,
        }

    def tombstone_application(self, job_id: str, *, reason: str, run_id: str) -> bool:
        _controlled(reason, REASON_CODES, "reason code")
        self.get_reconciliation_run(run_id)
        changed = self._tombstone_application(job_id, reason=reason, run_id=run_id)
        self.conn.commit()
        return changed

    def restore_application(self, job_id: str, *, run_id: str) -> bool:
        run = self.get_reconciliation_run(run_id)
        if run["action"] != "restore" or run["status"] != "running":
            raise ValueError("restore requires a running restore audit run")
        changed = self._restore_application(job_id, run_id=run_id)
        self.conn.commit()
        return changed

    def recoverable_applications(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT a.job_id, a.status, "
            "COALESCE(NULLIF(j.company, ''), a.company) AS company, "
            "COALESCE(NULLIF(j.title, ''), a.title) AS title, "
            "a.source, a.tombstoned_at, a.tombstone_reason, "
            "a.reconciliation_run_id, a.reconciliation_exempt "
            "FROM applications a LEFT JOIN jobs j ON j.id = a.job_id "
            "WHERE COALESCE(a.tombstoned_at, '') <> '' "
            "ORDER BY a.tombstoned_at DESC, a.job_id LIMIT ?",
            (max(1, min(int(limit), 500)),),
        )
        return [dict(row) for row in rows]

    def purge_reconciliation_decisions(self, older_than_days: int) -> int:
        days = int(older_than_days)
        if days < 1:
            raise ValueError("audit retention must be at least one day")
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400),
        )
        cur = self.conn.execute(
            "DELETE FROM reconciliation_decisions WHERE created_at < ?", (cutoff,),
        )
        self.conn.commit()
        return cur.rowcount