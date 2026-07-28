import sqlite3

import pytest

from jobscope.core import sqlite_runtime


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((3, 40, 1), False),
        ((3, 44, 5), False),
        ((3, 44, 6), True),
        ((3, 49, 1), False),
        ((3, 50, 6), False),
        ((3, 50, 7), True),
        ((3, 51, 2), False),
        ((3, 51, 3), True),
        ((3, 53, 4), True),
    ],
)
def test_safe_sqlite_versions(version, expected):
    assert sqlite_runtime.is_safe_sqlite(version) is expected


def test_require_safe_sqlite_rejects_affected_runtime(monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 49, 1))
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.49.1")

    with pytest.raises(RuntimeError, match=r"loaded 3\.49\.1"):
        sqlite_runtime.require_safe_sqlite()


def test_require_safe_sqlite_accepts_allowlisted_hosted_identity(monkeypatch):
    version = (3, 53, 4)
    trusted_source_id = next(iter(sqlite_runtime.TRUSTED_SOURCE_IDS[version]))
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.53.4")
    monkeypatch.setattr(sqlite_runtime, "source_id", lambda: trusted_source_id)
    monkeypatch.setenv(
        "JOBSCOPE_SQLITE_ARCHIVE_SHA256", sqlite_runtime.TRUSTED_ARCHIVE_SHA256,
    )

    sqlite_runtime.require_safe_sqlite(verify_identity=True)


def test_require_safe_sqlite_rejects_unallowlisted_source_identity(monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 53, 4))
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.53.4")
    monkeypatch.setattr(sqlite_runtime, "source_id", lambda: "unexpected source")
    monkeypatch.setenv(
        "JOBSCOPE_SQLITE_ARCHIVE_SHA256", sqlite_runtime.TRUSTED_ARCHIVE_SHA256,
    )

    with pytest.raises(RuntimeError, match="source identity"):
        sqlite_runtime.require_safe_sqlite(verify_identity=True)


def test_require_safe_sqlite_rejects_missing_archive_identity(monkeypatch):
    version = (3, 53, 4)
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.53.4")
    monkeypatch.setattr(
        sqlite_runtime, "source_id",
        lambda: next(iter(sqlite_runtime.TRUSTED_SOURCE_IDS[version])),
    )
    monkeypatch.delenv("JOBSCOPE_SQLITE_ARCHIVE_SHA256", raising=False)

    with pytest.raises(RuntimeError, match="archive identity missing"):
        sqlite_runtime.require_safe_sqlite(verify_identity=True)


def test_source_id_comes_from_loaded_library():
    with sqlite3.connect(":memory:") as connection:
        expected = connection.execute("SELECT sqlite_source_id()").fetchone()[0]

    assert sqlite_runtime.source_id() == expected