"""Tests for the static dashboard renderer (no network, no browser)."""
import os
import tempfile

from jobscope.deliver import render
from jobscope.core.config import load_config
from jobscope.core.model import Job
from jobscope.core.store import Store


def _cfg(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "s.db")
    cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
    cfg["output"]["public_dashboard_path"] = os.path.join(tmp, "public.html")
    return cfg


def _seed(store):
    job = Job(source="ats", title="Detection Engineer", company="Acme",
              url="https://x/ie", is_remote=True, remote_scope="Ireland").ensure_id()
    store.upsert_job(job)


def test_dashboard_exposes_remote_scope_facet():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        _seed(store)
        path = render.build(cfg, store, public=False)
        html = open(path, encoding="utf-8").read()
        store.close()
    assert "scopeSel" in html            # the hidden remote-scope <select> + JS wiring
    assert "remote_scope" in html        # the field is embedded in the dashboard DATA
    assert "Ireland" in html             # geo-restricted region surfaces in the facet/badge


def test_public_dashboard_keeps_remote_scope():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        _seed(store)
        path = render.build(cfg, store, public=True)
        html = open(path, encoding="utf-8").read()
        store.close()
    # remote_scope is public-safe: redaction must NOT strip it
    assert "remote_scope" in html
    assert "Ireland" in html
