import json
import os
import shutil
import subprocess
from pathlib import Path

from jobscope.deliver.site_crypto import encrypt_dashboard

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
        "companies": [],
        "reviews": [],
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


def test_python_dashboard_envelope_decrypts_with_node_browser_contract(tmp_path):
    payload = {
        "generated": "2026-07-26T00:00:00Z",
        "rows": [{"id": "job-1", "title": "Security Engineer"}],
        "applications": [],
    }
    envelope = encrypt_dashboard(
        payload,
        "browser-compatible-passphrase",
        salt=b"0123456789abcdef",
        iv=b"0123456789ab",
    )
    encrypted = tmp_path / "site.enc.json"
    encrypted.write_text(json.dumps(envelope), encoding="utf-8")
    script = """
const fs=require('node:fs'),crypto=require('node:crypto');
const b=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const salt=Buffer.from(b.salt,'base64'),iv=Buffer.from(b.iv,'base64'),all=Buffer.from(b.ct,'base64');
const key=crypto.pbkdf2Sync(Buffer.from(process.argv[2],'utf8'),salt,b.iter,32,'sha256');
const decipher=crypto.createDecipheriv('aes-256-gcm',key,iv);
decipher.setAuthTag(all.subarray(all.length-16));
process.stdout.write(Buffer.concat([decipher.update(all.subarray(0,-16)),decipher.final()]).toString('utf8'));
"""

    result = subprocess.run(
        [NODE, "-e", script, str(encrypted), "browser-compatible-passphrase"],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == payload