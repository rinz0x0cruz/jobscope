"""Validate cloud database snapshots and remove local-only campaign data."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Sequence

SQLITE_MAGIC = b"SQLite format 3\0"
REQUIRED_TABLES = frozenset({"applications", "jobs", "meta"})
LOCAL_ONLY_TABLES = (
    "outreach_campaign_runs",
    "outreach_campaign_targets",
    "outreach_campaigns",
    "outreach_suppressions",
)


class SnapshotValidationError(RuntimeError):
    """Raised when a file is not a healthy Jobscope SQLite snapshot."""


def validate_sqlite_snapshot(path: str | Path) -> None:
    snapshot = Path(path)
    try:
        with snapshot.open("rb") as handle:
            magic = handle.read(len(SQLITE_MAGIC))
    except OSError as exc:
        raise SnapshotValidationError(f"cannot read {snapshot}: {exc}") from exc
    if magic != SQLITE_MAGIC:
        raise SnapshotValidationError(f"{snapshot} is not a SQLite database")

    try:
        uri = f"{snapshot.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchall()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
    except sqlite3.Error as exc:
        raise SnapshotValidationError(f"cannot validate {snapshot}: {exc}") from exc

    if integrity != [("ok",)]:
        raise SnapshotValidationError(
            f"{snapshot} failed SQLite quick_check: {integrity!r}"
        )
    missing = REQUIRED_TABLES - tables
    if missing:
        names = ", ".join(sorted(missing))
        raise SnapshotValidationError(
            f"{snapshot} is not a Jobscope database; missing tables: {names}"
        )


def create_cloud_safe_snapshot(source: str | Path, destination: str | Path) -> None:
    """Copy a healthy DB while securely clearing campaign-local rows.

    SQLite backup produces a consistent destination even when the source uses a
    WAL. ``secure_delete`` plus ``VACUUM`` prevents deleted recipient/draft text
    from surviving in free pages before the copy is encrypted and uploaded.
    """
    source_path = Path(source)
    destination_path = Path(destination)
    validate_sqlite_snapshot(source_path)
    if source_path.resolve() == destination_path.resolve():
        raise SnapshotValidationError("cloud-safe snapshot destination must differ from source")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination_path.unlink(missing_ok=True)
        source_uri = f"{source_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source_connection:
            with sqlite3.connect(destination_path) as destination_connection:
                source_connection.backup(destination_connection)
                destination_connection.execute("PRAGMA secure_delete = ON")
                tables = {
                    row[0]
                    for row in destination_connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                for table in LOCAL_ONLY_TABLES:
                    if table in tables:
                        destination_connection.execute(f"DELETE FROM {table}")
                destination_connection.commit()
                destination_connection.execute("VACUUM")
        validate_sqlite_snapshot(destination_path)
    except (OSError, sqlite3.Error) as exc:
        destination_path.unlink(missing_ok=True)
        raise SnapshotValidationError(f"cannot create cloud-safe snapshot: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="decrypted SQLite snapshot to validate")
    parser.add_argument(
        "--cloud-copy", default="", metavar="PATH",
        help="write a validated copy with local campaign tables emptied and vacuumed",
    )
    args = parser.parse_args(argv)
    try:
        if args.cloud_copy:
            create_cloud_safe_snapshot(args.path, args.cloud_copy)
        else:
            validate_sqlite_snapshot(args.path)
    except SnapshotValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.cloud_copy:
        print(f"created cloud-safe Jobscope snapshot: {args.cloud_copy}")
    else:
        print(f"validated Jobscope SQLite snapshot: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())