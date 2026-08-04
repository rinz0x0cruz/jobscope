"""Create, verify, and restore encrypted full SQLite backup generations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from jobscope import __version__
from jobscope.core.snapshot import validate_sqlite_snapshot

MAGIC = b"JSDB"
FORMAT_VERSION = 1
ITERATIONS = 210_000
SALT_BYTES = 16
IV_BYTES = 12
TAG_BYTES = 16
HEADER_BYTES = len(MAGIC) + 1 + SALT_BYTES + IV_BYTES
ENCRYPTED_NAME = "jobscope.db.jsdb"
MANIFEST_NAME = "manifest.json"


class BackupError(RuntimeError):
    """Raised when a backup cannot be safely created, verified, or restored."""


def _require_key(key: str) -> bytes:
    if len(key) < 12:
        raise BackupError("backup key must contain at least 12 characters")
    return key.encode("utf-8")


def _derived_key(key: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS,
    ).derive(_require_key(key))


def encrypt_bytes(plaintext: bytes, key: str, *, salt: bytes | None = None,
                  iv: bytes | None = None) -> bytes:
    salt = salt or os.urandom(SALT_BYTES)
    iv = iv or os.urandom(IV_BYTES)
    if len(salt) != SALT_BYTES or len(iv) != IV_BYTES:
        raise BackupError("invalid backup encryption salt or IV")
    ciphertext = AESGCM(_derived_key(key, salt)).encrypt(iv, plaintext, None)
    return MAGIC + bytes([FORMAT_VERSION]) + salt + iv + ciphertext


def decrypt_bytes(encrypted: bytes, key: str) -> bytes:
    if len(encrypted) < HEADER_BYTES + TAG_BYTES or not encrypted.startswith(MAGIC):
        raise BackupError("backup is not a JSDB-encrypted file")
    if encrypted[len(MAGIC)] != FORMAT_VERSION:
        raise BackupError(
            f"unsupported JSDB version {encrypted[len(MAGIC)]}"
        )
    salt = encrypted[5:21]
    iv = encrypted[21:33]
    try:
        return AESGCM(_derived_key(key, salt)).decrypt(
            iv, encrypted[HEADER_BYTES:], None,
        )
    except InvalidTag as exc:
        raise BackupError("backup decryption failed") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sqlite_source_id() -> str:
    with closing(sqlite3.connect(":memory:")) as connection:
        return str(connection.execute("SELECT sqlite_source_id()").fetchone()[0])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_bytes(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
    _write_bytes(path, payload)


def _database_evidence(path: Path) -> dict[str, Any]:
    validate_sqlite_snapshot(path)
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        schema = connection.execute(
            """SELECT type, name, tbl_name, COALESCE(sql, '')
               FROM sqlite_schema
               WHERE name NOT LIKE 'sqlite_%'
               ORDER BY type, name"""
        ).fetchall()
        table_names = [
            row[0]
            for row in connection.execute(
                """SELECT name FROM sqlite_schema
                   WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                   ORDER BY name"""
            )
        ]
        table_counts = {}
        for table in table_names:
            quoted = table.replace('"', '""')
            table_counts[table] = int(
                connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
            )
    schema_payload = json.dumps(schema, ensure_ascii=True, separators=(",", ":"))
    return {
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "schema_sha256": _sha256_bytes(schema_payload.encode()),
        "table_count": len(table_counts),
        "tables": table_counts,
    }


def _copy_database(source: Path, destination: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        with closing(sqlite3.connect(destination)) as destination_connection:
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA journal_mode = DELETE")
            destination_connection.execute("PRAGMA synchronous = FULL")


def _load_manifest(generation: Path) -> dict[str, Any]:
    try:
        value = json.loads((generation / MANIFEST_NAME).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError(f"cannot read backup manifest: {exc}") from exc
    if not isinstance(value, dict) or value.get("format") != "jobscope-full-backup-v1":
        raise BackupError("backup manifest format is invalid")
    return value


def _verify_plaintext(plaintext: bytes, manifest: dict[str, Any], parent: Path) -> None:
    expected = manifest.get("database")
    if not isinstance(expected, dict) or _sha256_bytes(plaintext) != expected.get("sha256"):
        raise BackupError("decrypted database checksum does not match the manifest")
    with tempfile.TemporaryDirectory(prefix=".jobscope-verify-", dir=parent) as tmp:
        verify_path = Path(tmp) / "jobscope.db"
        _write_bytes(verify_path, plaintext)
        actual = _database_evidence(verify_path)
    if actual != expected:
        raise BackupError("decrypted database evidence does not match the manifest")


def verify_generation(path: str | Path, key: str) -> dict[str, Any]:
    generation = Path(path)
    manifest = _load_manifest(generation)
    encrypted_path = generation / ENCRYPTED_NAME
    try:
        encrypted = encrypted_path.read_bytes()
    except OSError as exc:
        raise BackupError(f"cannot read encrypted backup: {exc}") from exc
    expected = manifest.get("encrypted")
    actual = {"bytes": len(encrypted), "sha256": _sha256_bytes(encrypted)}
    if not isinstance(expected, dict) or actual != {
        "bytes": expected.get("bytes"), "sha256": expected.get("sha256"),
    }:
        raise BackupError("encrypted backup checksum does not match the manifest")
    plaintext = decrypt_bytes(encrypted, key)
    _verify_plaintext(plaintext, manifest, generation.parent)
    return manifest


def create_generation(source: str | Path, output_dir: str | Path, key: str,
                      *, artifact_identity: str = "unknown",
                      created_at: datetime | None = None) -> Path:
    source_path = Path(source)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    validate_sqlite_snapshot(source_path)
    stage = Path(tempfile.mkdtemp(prefix=".jobscope-backup-", dir=root))
    try:
        plaintext_path = stage / "jobscope.db"
        _copy_database(source_path, plaintext_path)
        database = _database_evidence(plaintext_path)
        encrypted = encrypt_bytes(plaintext_path.read_bytes(), key)
        encrypted_path = stage / ENCRYPTED_NAME
        _write_bytes(encrypted_path, encrypted)
        plaintext_path.unlink()

        stamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        generation_id = (
            f"{stamp.strftime('%Y%m%dT%H%M%SZ')}-{database['sha256'][:12]}-"
            f"{os.urandom(4).hex()}"
        )
        manifest = {
            "format": "jobscope-full-backup-v1",
            "backup_id": generation_id,
            "created_at": stamp.isoformat().replace("+00:00", "Z"),
            "artifact_identity": str(artifact_identity or "unknown")[:200],
            "jobscope_version": __version__,
            "sqlite": {
                "version": sqlite3.sqlite_version,
                "source_id": _sqlite_source_id(),
            },
            "database": database,
            "encrypted": {
                "bytes": len(encrypted),
                "sha256": _sha256_bytes(encrypted),
            },
        }
        _verify_plaintext(decrypt_bytes(encrypted, key), manifest, root)
        _write_json(stage / MANIFEST_NAME, manifest)

        final = root / generation_id
        if final.exists():
            raise BackupError(f"backup generation already exists: {generation_id}")
        stage.replace(final)
        return final
    except BaseException as exc:
        shutil.rmtree(stage, ignore_errors=True)
        if isinstance(exc, BackupError):
            raise
        if isinstance(exc, Exception):
            raise BackupError(f"backup generation failed: {exc}") from exc
        raise


def restore_generation(generation: str | Path, destination: str | Path, key: str) -> Path:
    generation_path = Path(generation)
    destination_path = Path(destination)
    if destination_path.exists():
        raise BackupError(f"restore destination already exists: {destination_path}")
    manifest = verify_generation(generation_path, key)
    encrypted = (generation_path / ENCRYPTED_NAME).read_bytes()
    plaintext = decrypt_bytes(encrypted, key)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_name(
        f".{destination_path.name}.restore-{os.urandom(4).hex()}"
    )
    try:
        _write_bytes(temporary, plaintext)
        actual = _database_evidence(temporary)
        if actual != manifest["database"]:
            raise BackupError("restored database evidence does not match the manifest")
        os.replace(temporary, destination_path)
        return destination_path
    except BaseException as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        if isinstance(exc, Exception):
            raise BackupError(f"backup restore failed: {exc}") from exc
        raise


def _key_from_environment() -> str:
    key = os.environ.get("JOBSCOPE_BACKUP_KEY", "")
    _require_key(key)
    return key


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("source")
    create.add_argument("output_dir")
    create.add_argument("--artifact", default=os.environ.get("JOBSCOPE_ARTIFACT_ID", "unknown"))
    verify = subparsers.add_parser("verify")
    verify.add_argument("generation")
    restore = subparsers.add_parser("restore")
    restore.add_argument("generation")
    restore.add_argument("destination")
    args = parser.parse_args(argv)
    try:
        key = _key_from_environment()
        if args.command == "create":
            generation = create_generation(
                args.source, args.output_dir, key, artifact_identity=args.artifact,
            )
            print(f"created verified backup generation: {generation}")
        elif args.command == "verify":
            manifest = verify_generation(args.generation, key)
            print(f"verified backup generation: {manifest['backup_id']}")
        else:
            restored = restore_generation(args.generation, args.destination, key)
            print(f"restored verified backup: {restored}")
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())