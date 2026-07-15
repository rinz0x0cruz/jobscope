import sqlite3

import pytest

from jobscope.core.snapshot import SnapshotValidationError, main, validate_sqlite_snapshot
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