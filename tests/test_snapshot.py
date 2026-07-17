import sqlite3

import pytest

from jobscope.core.snapshot import (
    SnapshotValidationError,
    create_cloud_safe_snapshot,
    main,
    validate_sqlite_snapshot,
)
from jobscope.core.store import Store


def test_validate_sqlite_snapshot_accepts_jobscope_database(tmp_path):
    path = tmp_path / "jobscope.db"
    Store(str(path)).close()

    validate_sqlite_snapshot(path)


def test_validate_sqlite_snapshot_rejects_non_sqlite_file(tmp_path):
    path = tmp_path / "jobscope.db"
    path.write_bytes(b"not a database")

    with pytest.raises(SnapshotValidationError, match="not a SQLite database"):
        validate_sqlite_snapshot(path)


def test_validate_sqlite_snapshot_rejects_unrelated_database(tmp_path):
    path = tmp_path / "other.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")

    with pytest.raises(SnapshotValidationError, match="missing tables"):
        validate_sqlite_snapshot(path)


def test_snapshot_validator_cli_reports_failure(tmp_path, capsys):
    path = tmp_path / "missing.db"

    assert main([str(path)]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_cloud_safe_snapshot_vacuums_local_campaign_data(tmp_path):
    source = tmp_path / "local.db"
    destination = tmp_path / "cloud.db"
    marker = "private-recipient-canary@example.test"
    with Store(str(source)) as store:
        campaign = store.create_outreach_campaign("Private campaign", 1)
        target = store.upsert_outreach_campaign_target(
            campaign["id"], "Private Co", "private co", rank_score=80,
        )
        store.set_outreach_campaign_draft(
            target["id"], selected_email=marker,
            subject="Private subject canary", body="Private body canary",
        )
        store.add_outreach_suppression("email", marker, reason="private reason canary")

    create_cloud_safe_snapshot(source, destination)

    with sqlite3.connect(destination) as connection:
        for table in (
            "outreach_campaigns", "outreach_campaign_targets", "outreach_campaign_runs",
            "outreach_suppressions",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert marker.encode() not in destination.read_bytes()
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outreach_campaigns").fetchone()[0] == 1