import os
import sqlite3
import tempfile

import pytest

from jobscope.core.model import Application
from jobscope.core.store import Store
from jobscope.apply import recovery
from jobscope.ingest import inbox, reconcile


def _store() -> Store:
    directory = tempfile.mkdtemp()
    return Store(os.path.join(directory, "audit.db"))


def test_audit_schema_migrates_existing_applications_table(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE applications ("
        "job_id TEXT PRIMARY KEY, status TEXT DEFAULT 'new', package_dir TEXT, "
        "resume_path TEXT, cover_path TEXT, applied_at TEXT, notes TEXT, updated TEXT, "
        "company TEXT, title TEXT, source TEXT, outreach_at TEXT, outreach_to TEXT, "
        "interview_at TEXT, salary_offered TEXT, offer_accepted TEXT)"
    )
    conn.execute(
        "INSERT INTO applications (job_id, status, company, source) "
        "VALUES ('mail:legacy', 'applied', 'Legacy Co', 'inbox')"
    )
    conn.commit()
    conn.close()

    store = Store(str(path))

    columns = {
        row["name"] for row in store.conn.execute("PRAGMA table_info(applications)")
    }
    tables = {
        row["name"] for row in store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    indexes = {
        row["name"] for row in store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert {
        "tombstoned_at", "tombstone_reason", "reconciliation_run_id",
        "reconciliation_exempt",
    } <= columns
    assert {"reconciliation_runs", "reconciliation_decisions"} <= tables
    assert {
        "idx_reconciliation_runs_started", "idx_reconciliation_decisions_run",
        "idx_reconciliation_decisions_application", "idx_applications_tombstone",
    } <= indexes
    baseline = store.reconciliation_runs()[0]
    assert baseline["baseline_only"] is True
    assert baseline["status"] == "completed"
    assert baseline["applications_before"] == baseline["applications_after"] == 1
    assert store.reconciliation_decisions(baseline["id"]) == []
    store.close()


def test_audit_run_tombstone_and_restore_lifecycle():
    store = _store()
    store.set_application(Application(
        job_id="mail:acme", status="applied", company="Acme", source="inbox",
    ))
    run = store.begin_reconciliation_run("recompute", "cli")

    decision = store.append_reconciliation_decision(
        run["id"], decision_type="application_tombstoned",
        application_id="mail:acme", base_job_id="mail:acme",
        old_status="applied", reason_code="orphan_mail_application",
        recoverable=True,
    )
    assert decision["id"] == f"{run['id']}:000001"
    assert store.tombstone_application(
        "mail:acme", reason="orphan_mail_application", run_id=run["id"],
    )
    store.finalize_reconciliation_run(
        run["id"], applications_after=0, events_after=0, tombstoned=1,
    )

    assert store.applications() == []
    assert store.get_application("mail:acme") is None
    hidden = store.get_application("mail:acme", include_tombstoned=True)
    assert hidden["tombstone_reason"] == "orphan_mail_application"
    assert hidden["reconciliation_run_id"] == run["id"]
    assert store.recoverable_applications()[0]["job_id"] == "mail:acme"
    assert store.reconciliation_runs()[0]["tombstoned_count"] == 1
    assert store.reconciliation_decisions(run["id"])[0]["recoverable"] is True

    restore = store.begin_reconciliation_run("restore", "user")
    assert store.restore_application("mail:acme", run_id=restore["id"])
    store.append_reconciliation_decision(
        restore["id"], decision_type="application_restored",
        application_id="mail:acme", base_job_id="mail:acme",
        new_status="applied", reason_code="recovery_requested",
    )
    store.finalize_reconciliation_run(
        restore["id"], applications_after=1, events_after=0, restored=1,
    )
    restored = store.get_application("mail:acme")
    assert restored["reconciliation_exempt"] == 1
    assert restored["tombstoned_at"] in (None, "")

    with pytest.raises(ValueError, match="reason code"):
        store.append_reconciliation_decision(
            restore["id"], decision_type="application_restored",
            reason_code="free form private explanation",
        )
    store.close()


def test_recovery_service_is_audited_idempotent_and_exempt():
    store = _store()
    store.set_application(Application(
        job_id="mail:recover", status="rejected", company="Acme", source="inbox",
    ))
    reconcile.recompute(store)
    assert store.get_application("mail:recover") is None

    result = recovery.restore_application(store, "mail:recover", initiator="user")

    assert result["restored"] is True
    restored = store.get_application("mail:recover")
    assert restored["reconciliation_exempt"] == 1
    run = store.get_reconciliation_run(result["run_id"])
    assert run["action"] == "restore" and run["restored_count"] == 1
    decisions = store.reconciliation_decisions(run["id"])
    assert len(decisions) == 1
    assert decisions[0]["decision_type"] == "application_restored"

    run_count = len(store.reconciliation_runs())
    assert recovery.restore_application(store, "mail:recover")["restored"] is False
    assert len(store.reconciliation_runs()) == run_count
    reconcile.recompute(store)
    assert store.get_application("mail:recover") is not None
    store.close()


def test_inbox_reconciliation_applies_configured_decision_retention():
    store = _store()
    store.set_application(Application(
        job_id="mail:retained", status="applied", company="Acme", source="inbox",
    ))
    reconcile.recompute(store)
    store.conn.execute(
        "UPDATE reconciliation_decisions SET created_at = '2000-01-01T00:00:00Z'"
    )
    store.conn.commit()
    cfg = {"retention": {"reconciliation_audit_days": 30}}

    assert inbox.run(cfg, store, reclassify=True) == 0

    assert len(store.reconciliation_runs()) == 2
    assert store.recoverable_applications()[0]["job_id"] == "mail:retained"
    assert sum(
        len(store.reconciliation_decisions(run["id"]))
        for run in store.reconciliation_runs()
    ) == 0
    store.close()