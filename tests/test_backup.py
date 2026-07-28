import errno
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from jobscope.core import backup
from jobscope.core.model import Job
from jobscope.core.snapshot import validate_sqlite_snapshot
from jobscope.core.store import Store

KEY = "test-only-long-backup-key"


def _database(path):
    with Store(str(path)) as store:
        store.upsert_job(
            Job(source="test", title="Security Engineer", company="Acme", url="u").ensure_id()
        )


def test_full_backup_roundtrip_has_evidence_and_no_plaintext(tmp_path):
    source = tmp_path / "source.db"
    generations = tmp_path / "generations"
    restored = tmp_path / "restore" / "jobscope.db"
    _database(source)

    generation = backup.create_generation(
        source, generations, KEY, artifact_identity="sha256:test",
        created_at=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
    )
    manifest = backup.verify_generation(generation, KEY)
    backup.restore_generation(generation, restored, KEY)

    assert {path.name for path in generation.iterdir()} == {
        backup.ENCRYPTED_NAME, backup.MANIFEST_NAME,
    }
    assert manifest["artifact_identity"] == "sha256:test"
    assert manifest["database"]["table_count"] == len(manifest["database"]["tables"])
    assert manifest["database"]["tables"]["jobs"] == 1
    assert len(manifest["database"]["sha256"]) == 64
    assert len(manifest["encrypted"]["sha256"]) == 64
    validate_sqlite_snapshot(restored)
    with sqlite3.connect(restored) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


@pytest.mark.parametrize("failed_name", [backup.ENCRYPTED_NAME, backup.MANIFEST_NAME])
def test_disk_full_never_promotes_partial_or_removes_prior_generation(
    tmp_path, monkeypatch, failed_name,
):
    source = tmp_path / "source.db"
    generations = tmp_path / "generations"
    _database(source)
    prior = backup.create_generation(source, generations, KEY)
    prior_manifest = json.loads((prior / backup.MANIFEST_NAME).read_text("utf-8"))
    original_write = backup._write_bytes

    def fail_write(path, value):
        if path.name == failed_name:
            raise OSError(errno.ENOSPC, "disk full")
        original_write(path, value)

    monkeypatch.setattr(backup, "_write_bytes", fail_write)
    with pytest.raises(backup.BackupError, match="disk full"):
        backup.create_generation(source, generations, KEY)

    assert [path for path in generations.iterdir() if not path.name.startswith(".")] == [prior]
    assert not list(generations.glob(".jobscope-backup-*"))
    assert backup.verify_generation(prior, KEY)["backup_id"] == prior_manifest["backup_id"]

    monkeypatch.setattr(backup, "_write_bytes", original_write)
    recovered = backup.create_generation(source, generations, KEY)
    assert backup.verify_generation(recovered, KEY)["backup_id"] == recovered.name


def test_corruption_and_wrong_key_fail_closed(tmp_path):
    source = tmp_path / "source.db"
    _database(source)
    generation = backup.create_generation(source, tmp_path / "generations", KEY)

    with pytest.raises(backup.BackupError, match="decryption failed"):
        backup.verify_generation(generation, "different-long-backup-key")

    encrypted = generation / backup.ENCRYPTED_NAME
    damaged = bytearray(encrypted.read_bytes())
    damaged[-20] ^= 1
    encrypted.write_bytes(damaged)
    with pytest.raises(backup.BackupError, match="checksum"):
        backup.verify_generation(generation, KEY)


def test_restore_refuses_to_replace_existing_database(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "existing.db"
    _database(source)
    destination.write_bytes(b"keep me")
    generation = backup.create_generation(source, tmp_path / "generations", KEY)

    with pytest.raises(backup.BackupError, match="already exists"):
        backup.restore_generation(generation, destination, KEY)

    assert destination.read_bytes() == b"keep me"


def test_interrupted_backup_cleans_staging_and_preserves_prior_generation(
    tmp_path, monkeypatch,
):
    source = tmp_path / "source.db"
    generations = tmp_path / "generations"
    _database(source)
    prior = backup.create_generation(source, generations, KEY)

    monkeypatch.setattr(
        backup, "_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        backup.create_generation(source, generations, KEY)

    assert [path for path in generations.iterdir() if not path.name.startswith(".")] == [prior]
    assert not list(generations.glob(".jobscope-backup-*"))
    assert backup.verify_generation(prior, KEY)["backup_id"] == prior.name