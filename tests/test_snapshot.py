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


def test_cloud_safe_snapshot_keeps_only_allowlisted_campaign_snapshot(tmp_path):
    source = tmp_path / "local.db"
    destination = tmp_path / "cloud.db"
    markers = (
        "private-recipient-canary@example.test",
        "private-application-canary",
        "private-source-target-canary",
        "private-parent-message-canary@example.test",
        "private-root-message-canary@example.test",
    )
    with Store(str(source)) as store:
        campaign = store.create_outreach_campaign(
            "Private follow-up campaign", 1, purpose="followup",
        )
        target = store.upsert_outreach_campaign_target(
            campaign["id"], "Private Co", "private co",
            application_job_id=markers[1], source_target_id=markers[2],
            parent_message_id=markers[3], root_message_id=markers[4],
            followup_number=1, rank_score=80,
        )
        store.set_outreach_campaign_draft(
            target["id"], selected_email=markers[0],
            subject="Private subject canary", body="Private body canary",
        )
        store.add_outreach_suppression(
            "email", markers[0], reason="private reason canary",
        )

    create_cloud_safe_snapshot(source, destination)

    with sqlite3.connect(destination) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        for table in (
            "outreach_campaigns", "outreach_campaign_targets", "outreach_campaign_runs",
            "outreach_suppressions",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        snapshot = connection.execute(
            "SELECT value FROM meta WHERE key = 'campaign:snapshot:v1'",
        ).fetchone()
        assert snapshot is not None
        assert markers[0] in snapshot[0]
        assert "Private follow-up campaign" in snapshot[0]
        assert "Private subject canary" in snapshot[0]
        assert "Private body canary" not in snapshot[0]
    snapshot_bytes = destination.read_bytes()
    for marker in markers[1:]:
        assert marker.encode() not in snapshot_bytes
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outreach_campaigns").fetchone()[0] == 1

    next_generation = tmp_path / "cloud-next.db"
    create_cloud_safe_snapshot(destination, next_generation)
    with sqlite3.connect(next_generation) as connection:
        carried = connection.execute(
            "SELECT value FROM meta WHERE key = 'campaign:snapshot:v1'",
        ).fetchone()
        assert carried == snapshot