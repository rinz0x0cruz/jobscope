import base64
import json

import pytest

from jobscope.deliver.publish_artifact import ArtifactValidationError, verify_artifact


def _write_inputs(tmp_path):
    public = {
        "generated": "2026-07-15T00:00:00Z", "total": 0, "rows": [],
        "overview": {"funnel": {}, "gaps": [], "considered": 0, "targets": []},
        "applications": [], "profile": None, "applied_outreach": [],
    }
    full = {
        **public,
        "total": 1,
        "rows": [{
            "id": "private-job-123", "title": "Unique Detection Engineer",
            "company": "Sensitive Example Corp", "location": "Remote",
            "url": "https://jobs.example/private-123", "base": "research",
            "rationale": "unique private rationale text", "brief": "private brief text",
            "description": "private job description text", "contacts": [],
        }],
    }
    envelope = {
        "v": 1, "kdf": "PBKDF2-SHA256", "iter": 210000,
        "salt": base64.b64encode(b"s" * 16).decode(),
        "iv": base64.b64encode(b"i" * 12).decode(),
        "ct": base64.b64encode(b"ciphertext" * 3 + b"t" * 16).decode(),
    }
    marker = {"v": 1, "url": "site.enc.json"}
    paths = {}
    for name, value in {
        "public": public, "full": full, "encrypted": envelope, "marker": marker,
    }.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<script src='assets/app.js'></script>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text(
        'const generated="2026-07-15T00:00:00Z",blob="site.enc.json";',
        encoding="utf-8",
    )
    (dist / "site.enc.json").write_bytes(paths["encrypted"].read_bytes())
    paths["dist"] = dist
    return paths


def test_verify_artifact_writes_hashed_manifest(tmp_path):
    paths = _write_inputs(tmp_path)

    manifest = verify_artifact(
        public_path=paths["public"], full_path=paths["full"],
        encrypted_path=paths["encrypted"], marker_path=paths["marker"],
        dist_path=paths["dist"], source_commit="abc123",
    )

    saved = json.loads((paths["dist"] / "deployment-manifest.json").read_text("utf-8"))
    assert manifest == saved
    assert saved["source_commit"] == "abc123"
    assert {"index.html", "assets/app.js", "site.enc.json"} <= set(saved["files"])


def test_verify_artifact_rejects_nonempty_public_payload(tmp_path):
    paths = _write_inputs(tmp_path)
    public = json.loads(paths["public"].read_text("utf-8"))
    public["rows"] = [{"title": "leak"}]
    paths["public"].write_text(json.dumps(public), encoding="utf-8")

    with pytest.raises(ArtifactValidationError, match=r"rows=\[\]"):
        verify_artifact(
            public_path=paths["public"], full_path=paths["full"],
            encrypted_path=paths["encrypted"], marker_path=paths["marker"],
            dist_path=paths["dist"],
        )


def test_verify_artifact_rejects_private_string_leak(tmp_path):
    paths = _write_inputs(tmp_path)
    asset = paths["dist"] / "assets" / "app.js"
    asset.write_text(
        asset.read_text("utf-8") + 'const leaked={title:"Unique Detection Engineer"};',
        encoding="utf-8",
    )

    with pytest.raises(ArtifactValidationError, match="private dashboard field leaked"):
        verify_artifact(
            public_path=paths["public"], full_path=paths["full"],
            encrypted_path=paths["encrypted"], marker_path=paths["marker"],
            dist_path=paths["dist"],
        )