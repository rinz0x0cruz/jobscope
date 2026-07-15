import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CRYPT = ROOT / "scripts" / "crypt-file.mjs"
SECURE_APPS = ROOT / "scripts" / "build-secure-apps.mjs"
TEMPLATE = ROOT / "scripts" / "apps-template.html"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for crypto compatibility tests")


def _crypt(mode: str, source: Path, target: Path, key: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, str(CRYPT), mode, str(source), str(target)],
        env={**os.environ, "JOBSCOPE_DB_KEY": key},
        capture_output=True,
        text=True,
        check=False,
    )


def test_jsdb_roundtrip_wrong_key_corruption_and_rotation(tmp_path):
    plaintext = tmp_path / "source.db"
    encrypted = tmp_path / "source.db.enc"
    decrypted = tmp_path / "decrypted.db"
    rotated = tmp_path / "rotated.db.enc"
    plaintext.write_bytes(b"SQLite format 3\0" + os.urandom(4096))

    assert _crypt("encrypt", plaintext, encrypted, "first-long-random-key").returncode == 0
    assert _crypt("decrypt", encrypted, decrypted, "first-long-random-key").returncode == 0
    assert decrypted.read_bytes() == plaintext.read_bytes()

    wrong = _crypt("decrypt", encrypted, tmp_path / "wrong.db", "wrong-long-random-key")
    assert wrong.returncode == 1
    assert "decryption failed" in wrong.stderr

    corrupted = bytearray(encrypted.read_bytes())
    corrupted[-20] ^= 0x01
    corrupt_path = tmp_path / "corrupt.db.enc"
    corrupt_path.write_bytes(corrupted)
    assert _crypt(
        "decrypt", corrupt_path, tmp_path / "corrupt.db", "first-long-random-key"
    ).returncode == 1

    assert _crypt("encrypt", decrypted, rotated, "second-long-random-key").returncode == 0
    rotated_plaintext = tmp_path / "rotated.db"
    assert _crypt(
        "decrypt", rotated, rotated_plaintext, "second-long-random-key"
    ).returncode == 0
    assert rotated_plaintext.read_bytes() == plaintext.read_bytes()
    assert _crypt(
        "decrypt", rotated, tmp_path / "old-key.db", "first-long-random-key"
    ).returncode == 1


def test_jsdb_rejects_unknown_version(tmp_path):
    plaintext = tmp_path / "source.db"
    encrypted = tmp_path / "source.db.enc"
    plaintext.write_bytes(b"payload")
    assert _crypt("encrypt", plaintext, encrypted, "version-test-key").returncode == 0
    envelope = bytearray(encrypted.read_bytes())
    envelope[4] = 2
    encrypted.write_bytes(envelope)

    result = _crypt("decrypt", encrypted, tmp_path / "out.db", "version-test-key")

    assert result.returncode == 1
    assert "unsupported JSDB version 2" in result.stderr


def test_node_dashboard_envelope_matches_browser_contract(tmp_path):
    dashboard = tmp_path / "dashboard.json"
    encrypted = tmp_path / "site.enc.json"
    payload = {
        "generated": "2026-07-15T00:00:00Z",
        "total": 1,
        "rows": [{"id": "job-1", "title": "Security Engineer"}],
        "overview": {"funnel": {}, "gaps": [], "considered": 0, "targets": []},
        "applications": [],
        "profile": None,
        "applied_outreach": [],
    }
    dashboard.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [NODE, str(SECURE_APPS), str(dashboard), str(TEMPLATE), "-", str(encrypted)],
        input="browser-compatible-passphrase",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    envelope = json.loads(encrypted.read_text("utf-8"))
    assert envelope["v"] == 1
    assert envelope["kdf"] == "PBKDF2-SHA256"
    assert envelope["iter"] == 210000
    assert all(envelope[key] for key in ("salt", "iv", "ct"))