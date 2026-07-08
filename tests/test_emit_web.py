"""Tests for `dashboard --emit-web` (render.emit_web): mirror the un-redacted
payload into web/src/data/dashboard.json so a plain `npm run dev`/`build` bakes
fresh data (issue #5). Offline."""
import json
import os

from jobscope.core.config import load_config
from jobscope.core.model import Job
from jobscope.core.store import Store
from jobscope.deliver import render


def test_emit_web_writes_unredacted_copy_when_web_tree_present(tmp_path, monkeypatch):
    cfg = load_config(None)
    cfg["output"]["db_path"] = str(tmp_path / "p.db")
    store = Store(cfg["output"]["db_path"])
    store.upsert_job(Job(source="indeed", title="Security Engineer", company="Acme",
                         url="u1", is_remote=True, score=82.0, tier="Strong",
                         rationale="Strong overlap; un-redacted marker").ensure_id())
    monkeypatch.chdir(tmp_path)

    # No web source tree -> no-op (safe when jobscope runs outside the repo).
    assert render.emit_web(cfg, store) is None

    # With the tree -> writes the un-redacted dev copy the SPA imports.
    os.makedirs(os.path.join("web", "src", "data"))
    path = render.emit_web(cfg, store)
    assert path == os.path.join("web", "src", "data", "dashboard.json")

    data = json.loads((tmp_path / "web" / "src" / "data" / "dashboard.json").read_text("utf-8"))
    assert data["rows"], "expected at least one row"
    # un-redacted: rationale is kept (the public build would strip it to "")
    assert data["rows"][0]["rationale"] == "Strong overlap; un-redacted marker"
    assert "applications" in data
    store.close()
