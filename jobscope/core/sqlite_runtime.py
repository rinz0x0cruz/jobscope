"""Fail-closed SQLite runtime policy for the hosted service."""
from __future__ import annotations

import sqlite3
import os
from contextlib import closing

TRUSTED_ARCHIVE_SHA256 = "0e9483900e92cd5de8fd48d16bf9200145a61f7fd5be542a5ac81d8a9516eb9c"  # pragma: allowlist secret
TRUSTED_SOURCE_IDS = {
    (3, 53, 4): frozenset({
        "2026-07-24 19:02:57 "
        "bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc",  # pragma: allowlist secret
    }),
}


def is_safe_sqlite(version: tuple[int, ...]) -> bool:
    """Return whether *version* contains SQLite's WAL-reset fix."""
    return (
        version >= (3, 51, 3)
        or version[:2] == (3, 50) and version >= (3, 50, 7)
        or version[:2] == (3, 44) and version >= (3, 44, 6)
    )


def require_safe_sqlite(*, verify_identity: bool = False) -> None:
    version = tuple(sqlite3.sqlite_version_info)
    if not is_safe_sqlite(version):
        raise RuntimeError(
            "hosted mode requires SQLite 3.51.3+ or an upstream fixed backport; "
            f"loaded {sqlite3.sqlite_version}"
        )
    if not verify_identity:
        return
    actual_source_id = source_id()
    if actual_source_id not in TRUSTED_SOURCE_IDS.get(version, frozenset()):
        raise RuntimeError(
            "hosted mode requires an allowlisted SQLite source identity; "
            f"loaded {sqlite3.sqlite_version} ({actual_source_id})"
        )
    archive_sha256 = os.environ.get("JOBSCOPE_SQLITE_ARCHIVE_SHA256", "").lower()
    if archive_sha256 != TRUSTED_ARCHIVE_SHA256:
        raise RuntimeError(
            "hosted mode requires the checksum-pinned SQLite source archive; "
            f"loaded archive identity {archive_sha256 or 'missing'}"
        )


def source_id() -> str:
    with closing(sqlite3.connect(":memory:")) as connection:
        return str(connection.execute("SELECT sqlite_source_id()").fetchone()[0])