from jobscope.cli import main
from jobscope.core.model import Application
from jobscope.core.store import Store
from jobscope.ingest import reconcile


def _tombstoned(path, *, status: str = "rejected") -> str:
    store = Store(str(path))
    job_id = "mail:cli-recover"
    store.set_application(Application(
        job_id=job_id, status=status, company="Acme", source="inbox",
    ))
    reconcile.recompute(store)
    store.close()
    return job_id


def test_applications_audit_and_confirmed_recovery(tmp_path, capsys):
    path = tmp_path / "cli.db"
    job_id = _tombstoned(path)

    assert main(["--db", str(path), "applications", "audit"]) == 0
    output = capsys.readouterr().out
    assert "recompute" in output and "1 recoverable" in output

    assert main([
        "--db", str(path), "applications", "recover", job_id,
    ]) == 2
    assert "--yes" in capsys.readouterr().err

    assert main([
        "--db", str(path), "applications", "recover", job_id, "--yes",
    ]) == 0
    store = Store(str(path))
    restored = store.get_application(job_id)
    assert restored["reconciliation_exempt"] == 1
    assert store.reconciliation_runs()[0]["action"] == "restore"
    store.close()


def test_purge_audit_removes_details_but_keeps_runs_and_tombstones(tmp_path):
    path = tmp_path / "retention.db"
    job_id = _tombstoned(path)
    store = Store(str(path))
    store.conn.execute(
        "UPDATE reconciliation_decisions SET created_at = '2000-01-01T00:00:00Z'"
    )
    store.conn.commit()
    run_count = len(store.reconciliation_runs())
    store.close()

    assert main([
        "--db", str(path), "purge", "--audit", "--older-than", "30",
    ]) == 0

    store = Store(str(path))
    assert len(store.reconciliation_runs()) == run_count
    assert store.get_application(job_id, include_tombstoned=True)["tombstoned_at"]
    assert sum(
        len(store.reconciliation_decisions(run["id"]))
        for run in store.reconciliation_runs()
    ) == 0
    store.close()


def test_application_purge_preserves_tombstones_until_confirmed(tmp_path, capsys):
    path = tmp_path / "tombstones.db"
    job_id = _tombstoned(path)
    store = Store(str(path))
    store.set_application(Application(job_id="manual:active", status="applied"))
    store.close()

    assert main(["--db", str(path), "purge", "--applications"]) == 0
    store = Store(str(path))
    assert store.get_application("manual:active") is None
    assert store.get_application(job_id, include_tombstoned=True) is not None
    store.close()

    assert main(["--db", str(path), "purge", "--tombstones"]) == 2
    assert "--yes" in capsys.readouterr().err
    assert main(["--db", str(path), "purge", "--tombstones", "--yes"]) == 0
    store = Store(str(path))
    assert store.get_application(job_id, include_tombstoned=True) is None
    store.close()