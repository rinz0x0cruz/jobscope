"""Read-only validation for encrypted cloud database snapshots."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Sequence

SQLITE_MAGIC = b"SQLite format 3\0"
REQUIRED_TABLES = frozenset({"applications", "jobs", "meta"})


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="decrypted SQLite snapshot to validate")
    args = parser.parse_args(argv)
    try:
        validate_sqlite_snapshot(args.path)
    except SnapshotValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"validated Jobscope SQLite snapshot: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())