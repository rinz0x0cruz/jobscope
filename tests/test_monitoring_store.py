import os
import sqlite3
import tempfile

import pytest

from jobscope.core.model import Job
from jobscope.core.store import Store
from jobscope.core.store import monitoring as monitoring_store


def _store() -> Store:
    directory = tempfile.mkdtemp()
    return Store(os.path.join(directory, "monitoring.db"))


def test_old_database_gains_monitoring_tables_additively():
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "old.db")
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, score REAL DEFAULT 0, company TEXT)"
    )
    connection.commit()
    connection.close()

    store = Store(path)
    tables = {row[0] for row in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}

    assert {"company_monitors", "company_monitor_jobs", "job_reviews"} <= tables
    store.close()


def test_monitor_upsert_merges_name_and_board_identity():
    store = _store()
    first = store.upsert_company_monitor(
        "Acme Technologies LLC", provider="greenhouse", slug="acme",
        careers_url="https://boards.greenhouse.io/acme", added_from="config",
    )
    same_name = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="application",
    )
    same_board = store.upsert_company_monitor(
        "Acme Security", provider="greenhouse", slug="acme", added_from="user",
    )

    assert first["id"] == same_name["id"] == same_board["id"]
    assert len(store.list_company_monitors()) == 1
    assert store.get_company_monitor(first["id"])["origins"] == ["config", "application", "user"]
    store.close()


def test_monitor_status_is_soft_and_history_is_preserved():
    store = _store()
    monitor = store.upsert_company_monitor("Acme", added_from="user")
    store.set_company_monitor_status(monitor["id"], "paused")
    assert store.list_company_monitors(status="paused")[0]["id"] == monitor["id"]
    store.set_company_monitor_status(monitor["id"], "removed")
    assert store.list_company_monitors() == []
    assert store.list_company_monitors(include_removed=True)[0]["status"] == "removed"
    store.close()


def test_monitor_links_and_dismissal_survive_job_pruning():
    store = _store()
    monitor = store.upsert_company_monitor(
        "Acme", provider="lever", slug="acme", added_from="user",
    )
    job = Job(source="ats", title="Security Engineer", company="Acme", url="https://x/1").ensure_id()
    store.upsert_job(job)
    store.link_monitor_job(monitor["id"], job.id, "2026-07-16T00:00:00Z")
    pending = store.ensure_job_review(job.id, origins=["monitored"])
    assert pending["state"] == "pending" and pending["monitor_ids"] == [monitor["id"]]

    store.set_job_review(job.id, "dismissed", origins=["monitored"])
    store.delete_jobs([job.id])

    dismissed = store.get_job_review(job.id)
    assert dismissed["state"] == "dismissed"
    assert dismissed["origins"] == ["monitored"]
    assert dismissed["monitor_ids"] == [monitor["id"]]
    store.close()


def test_reconcile_monitor_jobs_closes_only_missing_linked_jobs():
    store = _store()
    monitor = store.upsert_company_monitor(
        "Acme", provider="ashby", slug="acme", added_from="config",
    )
    current = Job(source="ats", title="Current", company="Acme", url="https://x/current").ensure_id()
    removed = Job(source="ats", title="Removed", company="Acme", url="https://x/removed").ensure_id()
    store.upsert_job(current)
    store.upsert_job(removed)
    store.link_monitor_job(monitor["id"], current.id)
    store.link_monitor_job(monitor["id"], removed.id)

    assert store.reconcile_monitor_jobs(monitor["id"], {current.id}) == 1
    assert store.get_job(current.id).status == "open"
    assert store.get_job(removed.id).status == "closed"
    assert store.reconcile_monitor_jobs(monitor["id"], set()) == 0
    store.close()


def test_monitor_summary_joins_health_and_review_counts():
    store = _store()
    monitor = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="config",
    )
    pending_job = Job(source="ats", title="One", company="Acme", url="https://x/1").ensure_id()
    saved_job = Job(source="ats", title="Two", company="Acme", url="https://x/2").ensure_id()
    for job in (pending_job, saved_job):
        store.upsert_job(job)
        store.update_score(job.id, 80, "Strong", "fit")
        store.link_monitor_job(monitor["id"], job.id)
    store.set_job_review(pending_job.id, "pending", origins=["monitored"])
    store.set_job_review(saved_job.id, "saved", origins=["monitored"])
    store.set_source_health(
        f"monitor:{monitor['id']}", provider="greenhouse", slug="acme",
        status="ok", item_count=14,
    )

    summary = store.company_monitor_summaries()[0]
    assert summary["health_status"] == "ok" and summary["board_count"] == 14
    assert summary["open_matches"] == 2
    assert summary["pending_count"] == 1 and summary["saved_count"] == 1
    store.close()


def test_monitoring_action_batch_rolls_back_on_invalid_action():
    store = _store()
    monitor = store.upsert_company_monitor("Acme", added_from="user")

    with pytest.raises(ValueError, match="unsupported monitoring action"):
        store.apply_monitoring_actions([
            {"type": "monitor.status", "monitor_id": monitor["id"], "status": "paused"},
            {"type": "unknown"},
        ])

    assert store.get_company_monitor(monitor["id"])["status"] == "active"
    store.close()


def test_review_origin_sync_preserves_decision_timestamp(monkeypatch):
    store = _store()
    job = Job(source="ats", title="Security Engineer", company="Acme", url="https://x/1").ensure_id()
    store.upsert_job(job)
    monkeypatch.setattr(monitoring_store, "now_iso", lambda: "2026-07-16T10:00:00Z")
    saved = store.set_job_review(job.id, "saved", origins=["discovery"])

    monkeypatch.setattr(monitoring_store, "now_iso", lambda: "2026-07-17T10:00:00Z")
    synced = store.ensure_job_review(job.id, origins=["monitored"])

    assert saved["reviewed_at"] == "2026-07-16T10:00:00Z"
    assert synced["reviewed_at"] == saved["reviewed_at"]
    assert synced["origins"] == ["discovery", "monitored"]
    store.close()


def test_monitor_identity_merge_preserves_origins_from_both_rows():
    store = _store()
    unresolved = store.upsert_company_monitor("Acme", added_from="application")
    resolved = store.upsert_company_monitor(
        "Acme Holdings", provider="greenhouse", slug="acme-security-careers",
        added_from="config",
    )

    merged = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme-security-careers",
        added_from="user",
    )

    assert merged["id"] == resolved["id"]
    assert merged["id"] != unresolved["id"]
    assert merged["origins"] == ["config", "application", "user"]
    assert len(store.list_company_monitors()) == 1
    store.close()