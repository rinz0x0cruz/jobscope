"""Refresh & Publish pipeline + serve endpoint guards.

Covers the once-per-day guard, the shared ``perform_refresh`` wiring (inbox ->
match -> render -> publish, with the optional board scan), and the loopback /
CSRF-token guard on the ``/api/refresh`` endpoint. Fully offline: the networked
steps and the publish subprocess are stubbed.
"""
import datetime as dt
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request

import pytest

from jobscope.analyze import match as match_mod
from jobscope.core.config import load_config
from jobscope.core.store import Store
from jobscope.deliver import serve
from jobscope.ingest import inbox as inbox_mod
from jobscope.ingest import scrape as scrape_mod


def _cfg(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "p.db")
    cfg["output"]["dashboard_path"] = os.path.join(tmp, "dash.html")
    return cfg


@pytest.fixture(autouse=True)
def _reset_state():
    serve._STATE.update(state="idle", step="", message="", started="",
                        finished="", last_date="")
    yield


def _patch_pipeline(monkeypatch):
    calls = {"inbox": 0, "match": 0, "scrape": 0, "publish": 0, "since": None}

    def fake_inbox(cfg, store, **kw):
        calls["inbox"] += 1
        calls["since"] = kw.get("since")
        return 0

    def fake_match(cfg, store):
        calls["match"] += 1
        return 0

    def fake_scrape(cfg, store):
        calls["scrape"] += 1
        return 0

    def fake_publish(cfg):
        calls["publish"] += 1
        return ""

    monkeypatch.setattr(inbox_mod, "run", fake_inbox)
    monkeypatch.setattr(match_mod, "run", fake_match)
    monkeypatch.setattr(scrape_mod, "run", fake_scrape)
    monkeypatch.setattr(serve, "_publish", fake_publish)
    return calls


def test_perform_refresh_runs_and_stamps(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        Store(cfg["output"]["db_path"]).close()  # init schema
        calls = _patch_pipeline(monkeypatch)

        res = serve.perform_refresh(cfg, force=False)

        assert res["state"] == "done"
        assert calls["inbox"] == 1 and calls["match"] == 1 and calls["publish"] == 1
        assert calls["scrape"] == 0  # full scan off by default
        days = cfg["serve"]["inbox_days"]
        assert calls["since"] == (dt.date.today() - dt.timedelta(days=days)).isoformat()
        with Store(cfg["output"]["db_path"]) as store:
            assert store.meta_get("refresh:last_date") == dt.date.today().isoformat()


def test_per_day_guard_skips(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg["output"]["db_path"]) as store:
            store.meta_set("refresh:last_date", dt.date.today().isoformat())
        calls = _patch_pipeline(monkeypatch)

        res = serve.perform_refresh(cfg, force=False)

        assert res["state"] == "skipped"
        assert calls["inbox"] == 0 and calls["match"] == 0 and calls["publish"] == 0


def test_force_overrides_guard(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg["output"]["db_path"]) as store:
            store.meta_set("refresh:last_date", dt.date.today().isoformat())
        calls = _patch_pipeline(monkeypatch)

        res = serve.perform_refresh(cfg, force=True)

        assert res["state"] == "done"
        assert calls["inbox"] == 1 and calls["match"] == 1 and calls["publish"] == 1


def test_full_scan_toggle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        Store(cfg["output"]["db_path"]).close()
        calls = _patch_pipeline(monkeypatch)

        serve.perform_refresh(cfg, force=True, full_scan=True)

        assert calls["scrape"] == 1


# ---- endpoints / CSRF guard -------------------------------------------------

def _serve_bg(cfg):
    httpd, page, token, _on = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1], token, thread


def _req(method, url, headers=None, data=None):
    body = data.encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=body)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def test_endpoints_and_csrf_guard(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        Store(cfg["output"]["db_path"]).close()
        # Never run the real worker in this test; only exercise routing + guard.
        monkeypatch.setattr(serve, "_run_refresh", lambda *a, **k: None)
        httpd, port, token, thread = _serve_bg(cfg)
        base = f"http://127.0.0.1:{port}"
        try:
            status, body = _req("GET", base + "/api/token")
            assert status == 200 and body["enabled"] is True and body["token"] == token

            status, body = _req("GET", base + "/api/status")
            assert status == 200 and body["state"] == "idle"

            # No token -> forbidden.
            status, _ = _req("POST", base + "/api/refresh", data="{}")
            assert status == 403

            # Valid token but cross-origin -> forbidden.
            status, _ = _req("POST", base + "/api/refresh", data="{}",
                             headers={"X-Refresh-Token": token,
                                      "Origin": "https://evil.example"})
            assert status == 403

            # Valid token + loopback origin -> accepted.
            status, body = _req("POST", base + "/api/refresh", data="{}",
                                headers={"X-Refresh-Token": token, "Origin": base,
                                         "Content-Type": "application/json"})
            assert status == 200 and body["state"] in ("started", "busy")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


def test_refresh_disabled_returns_403(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        cfg["serve"]["refresh_enabled"] = False
        Store(cfg["output"]["db_path"]).close()
        httpd, port, token, thread = _serve_bg(cfg)
        base = f"http://127.0.0.1:{port}"
        try:
            status, body = _req("GET", base + "/api/token")
            assert status == 200 and body["enabled"] is False
            status, _ = _req("POST", base + "/api/refresh", data="{}",
                             headers={"X-Refresh-Token": token, "Origin": base})
            assert status == 403
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)
