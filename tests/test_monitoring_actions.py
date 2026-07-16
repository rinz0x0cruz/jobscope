import os
import json
import tempfile

import pytest

from jobscope.apply import monitoring, recovery
from jobscope.core.config import load_config
from jobscope.core.model import Application, Job, Resume
from jobscope.core.store import Store
from jobscope.ingest import ats, reconcile


def _setup():
    directory = tempfile.mkdtemp()
    cfg = load_config(os.path.join(directory, "missing-config.yaml"))
    cfg["output"]["db_path"] = os.path.join(directory, "actions.db")
    cfg["search"]["scope_to_home"] = False
    cfg["search"]["terms"] = ["Security Engineer"]
    cfg["apply"]["outreach"]["monitor_scan"]["enabled"] = False
    store = Store(cfg["output"]["db_path"])
    store.save_resume(Resume(
        full_name="Mohit", skills=["python", "aws", "security"],
        titles=["Security Engineer"], seniority="junior",
    ), name="research")
    return cfg, store


def _board():
    return ats.BoardFetchResult(
        "Acme", "greenhouse", "acme", ats.BoardStatus.OK,
        [Job(source="ats", title="Security Engineer", company="Acme",
             location="Remote", is_remote=True, url="https://x/1",
             description="Python AWS security").ensure_id()],
        attempts=1, status_code=200,
    )


def test_action_batch_adds_monitor_and_sets_review_atomically(monkeypatch):
    cfg, store = _setup()
    job = Job(source="indeed", title="Engineer", company="Beta", url="https://x/b").ensure_id()
    store.upsert_job(job)
    store.set_job_review(job.id, "pending", origins=["discovery"])
    monkeypatch.setattr(ats, "resolve_board_result", lambda *_a, **_k: ats.BoardResolution(
        "Acme", ats.ResolutionStatus.RESOLVED, "greenhouse", "acme",
        "https://boards.greenhouse.io/acme",
    ))

    result = monitoring.apply_actions(cfg, store, [
        {"type": "monitor.upsert", "company": "Acme"},
        {"type": "review.set", "job_id": job.id, "state": "saved"},
    ])

    assert result["ok"] and result["applied"] == 2
    assert store.get_company_monitor("Acme")["resolution_status"] == "resolved"
    assert store.get_job_review(job.id)["state"] == "saved"
    store.close()


def test_action_validation_rejects_unknown_fields_before_mutation(monkeypatch):
    cfg, store = _setup()
    monkeypatch.setattr(ats, "resolve_board_result", lambda *_a, **_k: ats.BoardResolution(
        "Acme", ats.ResolutionStatus.UNRESOLVED,
    ))
    with pytest.raises(ValueError, match="unknown fields"):
        monitoring.apply_actions(cfg, store, [
            {"type": "monitor.upsert", "company": "Acme"},
            {"type": "review.set", "job_id": "j", "state": "saved", "evil": True},
        ])
    assert store.list_company_monitors() == []
    store.close()


def test_scan_actions_run_after_monitor_status_commit(monkeypatch):
    cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _board())

    result = monitoring.apply_actions(cfg, store, [
        {"type": "monitor.status", "monitor_id": company["id"], "status": "active"},
        {"type": "monitor.scan", "monitor_id": company["id"]},
    ])

    assert result["scans"][0]["ok"]
    assert result["reviews"][0]["state"] == "pending"
    assert result["rows"][0]["title"] == "Security Engineer"
    store.close()


def test_resolve_company_previews_ranked_matches(monkeypatch):
    cfg, store = _setup()
    monkeypatch.setattr(ats, "resolve_board_result", lambda *_a, **_k: ats.BoardResolution(
        "Acme", ats.ResolutionStatus.RESOLVED, "greenhouse", "acme",
        "https://boards.greenhouse.io/acme",
    ))
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _board())

    result = monitoring.resolve_company(cfg, store, company="Acme")

    assert result["ok"] and result["count"] == 1 and result["matched"] == 1
    assert result["results"][0]["title"] == "Security Engineer"
    assert store.list_company_monitors() == []
    store.close()


def test_action_file_applies_validated_batch(tmp_path):
    cfg, store = _setup()
    job = Job(source="indeed", title="Engineer", company="Acme", url="https://x/file").ensure_id()
    store.upsert_job(job)
    store.set_job_review(job.id, "pending", origins=["discovery"])
    path = tmp_path / "actions.json"
    path.write_text(json.dumps({
        "actions": [{"type": "review.set", "job_id": job.id, "state": "saved"}],
    }), encoding="utf-8")

    assert monitoring.run_actions_file(cfg, store, str(path)) == 0
    assert store.get_job_review(job.id)["state"] == "saved"
    store.close()


def test_monitor_upsert_links_discovery_job_and_preserves_review_state(monkeypatch):
    cfg, store = _setup()
    job = Job(source="indeed", title="Engineer", company="Acme", url="https://jobs.lever.co/acme/1").ensure_id()
    store.upsert_job(job)
    store.set_job_review(job.id, "saved", origins=["discovery"])
    monkeypatch.setattr(ats, "resolve_board_result", lambda *_a, **_k: ats.BoardResolution(
        "Acme", ats.ResolutionStatus.RESOLVED, "lever", "acme", "https://jobs.lever.co/acme",
    ))

    monitoring.apply_actions(cfg, store, [{
        "type": "monitor.upsert", "company": "Acme",
        "careers_url": job.url, "job_id": job.id,
    }])

    review = store.get_job_review(job.id)
    assert review["state"] == "saved"
    assert review["origins"] == ["discovery", "monitored"]
    assert len(review["monitor_ids"]) == 1
    store.close()


def test_application_restore_action_owns_audit_run_and_is_idempotent():
    cfg, store = _setup()
    job_id = "mail:action-recover"
    store.set_application(Application(
        job_id=job_id, status="applied", company="Acme", source="inbox",
    ))
    reconcile.recompute(store)

    result = monitoring.apply_actions(cfg, store, [
        {"type": "application.restore", "job_id": job_id},
    ])

    assert result["ok"] and result["applied"] == 1
    assert result["results"][0]["restored"] is True
    assert result["applications"][0]["job_id"] == job_id
    assert result["activity_audit"]["recent_runs"][0]["action"] == "restore"
    assert result["activity_audit"]["recoverable_applications"] == []
    assert store.get_application(job_id)["reconciliation_exempt"] == 1

    repeated = monitoring.apply_actions(cfg, store, [
        {"type": "application.restore", "job_id": job_id},
    ])
    assert repeated["results"][0]["restored"] is False
    with pytest.raises(ValueError, match="unknown fields"):
        monitoring.apply_actions(cfg, store, [{
            "type": "application.restore", "job_id": job_id, "run_id": "client-run",
        }])
    store.close()


def test_restore_failure_rolls_back_the_entire_action_batch(monkeypatch):
    cfg, store = _setup()
    review_job = Job(
        source="indeed", title="Engineer", company="Beta", url="https://x/review",
    ).ensure_id()
    store.upsert_job(review_job)
    store.set_job_review(review_job.id, "pending", origins=["discovery"])
    recover_job = "mail:batch-recover"
    store.set_application(Application(
        job_id=recover_job, status="applied", company="Acme", source="inbox",
    ))
    reconcile.recompute(store)

    def fail_restore(*_args, **_kwargs):
        raise RuntimeError("injected restore failure")

    monkeypatch.setattr(recovery, "_restore_application_in_run", fail_restore)

    with pytest.raises(RuntimeError, match="injected restore failure"):
        monitoring.apply_actions(cfg, store, [
            {"type": "review.set", "job_id": review_job.id, "state": "saved"},
            {"type": "application.restore", "job_id": recover_job},
        ])

    assert store.get_job_review(review_job.id)["state"] == "pending"
    assert store.get_application(recover_job) is None
    assert store.get_application(recover_job, include_tombstoned=True)["tombstoned_at"]
    latest = store.reconciliation_runs()[0]
    assert latest["action"] == "restore" and latest["status"] == "failed"
    assert store.reconciliation_decisions(latest["id"]) == []
    store.close()