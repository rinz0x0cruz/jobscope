"""Dashboard JSON data contract (`dashboard --emit-json`).

Pins the shape the web build consumes and confirms the public redaction is applied
to the emitted JSON exactly as it is to the HTML dashboard. Fully offline.
"""
import json
import os
import tempfile

from jobscope import render
from jobscope.config import load_config
from jobscope.model import Job
from jobscope.store import Store


def _seed(store):
    store.upsert_job(Job(
        source="indeed", title="Senior Security Engineer", company="Acme",
        url="https://jobs.example/acme-sse", is_remote=True, remote_scope="global",
        score=82.0, tier="Strong", resume_base="research",
        rationale="Strong overlap; ~1.7y experience (junior)").ensure_id())


def test_emit_json_shape():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        store = Store(cfg["output"]["db_path"])
        _seed(store)

        path = render.emit_json(cfg, store, public=False)
        assert os.path.basename(path) == "dashboard.json"
        data = json.load(open(path, encoding="utf-8"))
        assert {"generated", "total", "rows", "overview"} <= set(data)
        assert data["total"] == 1 and len(data["rows"]) == 1
        row = data["rows"][0]
        # core public-safe fields the web card needs
        for key in ("id", "title", "company", "location", "tier", "score",
                    "remote_scope", "url", "salary", "enrich", "brief"):
            assert key in row, key
        assert row["title"] == "Senior Security Engineer"
        # rationale persists via upsert; resume_base is assigned by `match`, not upsert
        assert row["rationale"]
        store.close()


def test_emit_json_public_is_redacted():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
        cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
        store = Store(cfg["output"]["db_path"])
        _seed(store)

        path = render.emit_json(cfg, store, public=True)
        assert os.path.basename(path) == "dashboard.public.json"
        pub = json.load(open(path, encoding="utf-8"))
        row = pub["rows"][0]
        assert row["base"] == "" and row["rationale"] == "" and row["contacts"] == []
        # public-safe info is kept
        assert row["title"] == "Senior Security Engineer" and row["company"] == "Acme"
        store.close()
