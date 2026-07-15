"""Validate an isolated encrypted dashboard artifact before publication."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


class ArtifactValidationError(RuntimeError):
    """Raised when a publication artifact violates its privacy contract."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"cannot read JSON {path}: {exc}") from exc


def _validate_public(data: Any) -> None:
    if not isinstance(data, dict):
        raise ArtifactValidationError("public dashboard payload is not an object")
    expected = {
        "total": 0,
        "rows": [],
        "applications": [],
        "profile": None,
        "applied_outreach": [],
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise ArtifactValidationError(
                f"public dashboard must contain {key}={value!r}"
            )
    overview = data.get("overview")
    if not isinstance(overview, dict):
        raise ArtifactValidationError("public dashboard overview is missing")
    for key, value in {"funnel": {}, "gaps": [], "considered": 0, "targets": []}.items():
        if overview.get(key) != value:
            raise ArtifactValidationError(
                f"public dashboard overview must contain {key}={value!r}"
            )
    if not isinstance(data.get("generated"), str) or not data["generated"]:
        raise ArtifactValidationError("public dashboard generated marker is missing")


def _decode_field(blob: dict, name: str, expected_length: int | None = None) -> bytes:
    value = blob.get(name)
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"encrypted envelope field {name!r} is missing")
    try:
        decoded = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ArtifactValidationError(
            f"encrypted envelope field {name!r} is not valid base64"
        ) from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise ArtifactValidationError(
            f"encrypted envelope field {name!r} must be {expected_length} bytes"
        )
    return decoded


def _validate_envelope(blob: Any) -> None:
    if not isinstance(blob, dict):
        raise ArtifactValidationError("encrypted dashboard envelope is not an object")
    if blob.get("v") != 1 or blob.get("kdf") != "PBKDF2-SHA256":
        raise ArtifactValidationError("unsupported encrypted dashboard envelope")
    if not isinstance(blob.get("iter"), int) or blob["iter"] < 210_000:
        raise ArtifactValidationError("encrypted dashboard PBKDF2 iteration count is too low")
    _decode_field(blob, "salt", 16)
    _decode_field(blob, "iv", 12)
    if len(_decode_field(blob, "ct")) <= 16:
        raise ArtifactValidationError("encrypted dashboard ciphertext is too short")


def _add_marker(markers: set[tuple[str, str]], key: str, value: Any) -> None:
    if isinstance(value, str) and len(value.strip()) >= 8:
        markers.add((key, value))


def _private_markers(full: dict) -> set[tuple[str, str]]:
    markers: set[tuple[str, str]] = set()
    for row in full.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for key in ("id", "title", "company", "location", "url", "base",
                    "rationale", "brief", "description"):
            _add_marker(markers, key, row.get(key))
        for contact in row.get("contacts") or []:
            if isinstance(contact, dict):
                for key in ("name", "title", "url"):
                    _add_marker(markers, key, contact.get(key))

    for application in full.get("applications") or []:
        if not isinstance(application, dict):
            continue
        for key in ("job_id", "company", "title", "applied_at", "interview_at",
                    "salary_offered", "offer_accepted"):
            _add_marker(markers, key, application.get(key))
        for event in application.get("timeline") or []:
            if not isinstance(event, dict):
                continue
            for key in ("subject", "from", "summary"):
                _add_marker(markers, key, event.get(key))

    profile = full.get("profile") or {}
    if isinstance(profile, dict):
        for key in ("resume", "name"):
            _add_marker(markers, key, profile.get(key))
        for key in ("search_terms", "locations", "top_skills"):
            for value in profile.get(key) or []:
                _add_marker(markers, key, value)

    for company in full.get("applied_outreach") or []:
        if not isinstance(company, dict):
            continue
        for key in ("company", "domain"):
            _add_marker(markers, key, company.get(key))
        for contact in company.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            for key in ("email", "note"):
                _add_marker(markers, key, contact.get(key))

    overview = full.get("overview") or {}
    for value in overview.get("targets") or []:
        _add_marker(markers, "targets", value)
    return markers


def _serialized_markers(key: str, value: str) -> tuple[str, ...]:
    encoded_key = json.dumps(key, ensure_ascii=False)
    encoded_values = {
        json.dumps(value, ensure_ascii=False),
        json.dumps(value, ensure_ascii=True),
    }
    return tuple(
        marker
        for encoded_value in encoded_values
        for marker in (
            f"{key}:{encoded_value}", f"{encoded_key}:{encoded_value}",
            f"{key}:[{encoded_value}", f"{encoded_key}:[{encoded_value}",
        )
    )


def _text_assets(dist: Path) -> list[Path]:
    suffixes = {".css", ".html", ".js", ".json", ".map", ".txt", ".xml"}
    return [
        path for path in dist.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
        and path.name not in {"deployment-manifest.json", "site.enc.json"}
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(*, public_path: str | Path, full_path: str | Path,
                    encrypted_path: str | Path, marker_path: str | Path,
                    dist_path: str | Path, source_commit: str = "") -> dict[str, Any]:
    public_file = Path(public_path)
    full_file = Path(full_path)
    encrypted_file = Path(encrypted_path)
    marker_file = Path(marker_path)
    dist = Path(dist_path)

    public = _load_json(public_file)
    full = _load_json(full_file)
    envelope = _load_json(encrypted_file)
    marker = _load_json(marker_file)
    _validate_public(public)
    if not isinstance(full, dict):
        raise ArtifactValidationError("full dashboard payload is not an object")
    _validate_envelope(envelope)
    if marker != {"v": 1, "url": "site.enc.json"}:
        raise ArtifactValidationError("encrypted marker must point to site.enc.json")

    index = dist / "index.html"
    bundled_envelope = dist / "site.enc.json"
    if not index.is_file():
        raise ArtifactValidationError("artifact is missing index.html")
    if not bundled_envelope.is_file():
        raise ArtifactValidationError("artifact is missing site.enc.json")
    if _sha256(bundled_envelope) != _sha256(encrypted_file):
        raise ArtifactValidationError("bundled encrypted payload differs from its source")

    assets = _text_assets(dist)
    asset_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in assets
    )
    if public["generated"] not in asset_text:
        raise ArtifactValidationError("built assets do not contain the public payload marker")
    if "site.enc.json" not in asset_text:
        raise ArtifactValidationError("built assets do not contain the encrypted payload pointer")
    for key, value in sorted(_private_markers(full), key=lambda item: len(item[1]), reverse=True):
        if any(marker in asset_text for marker in _serialized_markers(key, value)):
            raise ArtifactValidationError(
                f"private dashboard field leaked into built assets: {key}={value[:80]!r}"
            )

    files = {
        path.relative_to(dist).as_posix(): _sha256(path)
        for path in sorted(dist.rglob("*")) if path.is_file()
        and path.name != "deployment-manifest.json"
    }
    manifest = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": source_commit,
        "public_payload_sha256": _sha256(public_file),
        "encrypted_payload_sha256": _sha256(encrypted_file),
        "files": files,
    }
    fd, temporary = tempfile.mkstemp(prefix="deployment-manifest.", suffix=".tmp", dir=dist)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, sort_keys=True, separators=(",", ":"))
        os.replace(temporary, dist / "deployment-manifest.json")
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", required=True)
    parser.add_argument("--full", required=True)
    parser.add_argument("--encrypted", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--dist", required=True)
    parser.add_argument("--source-commit", default="")
    args = parser.parse_args(argv)
    try:
        manifest = verify_artifact(
            public_path=args.public, full_path=args.full,
            encrypted_path=args.encrypted, marker_path=args.marker,
            dist_path=args.dist, source_commit=args.source_commit,
        )
    except ArtifactValidationError as exc:
        print(f"error: {exc}")
        return 1
    print(f"validated publish artifact: {len(manifest['files'])} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())