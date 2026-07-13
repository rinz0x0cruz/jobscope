"""Tests for the on-demand company scout (ats.resolve_board + apply.scout).

Network is mocked at ``jobscope.core.httpx.get_json`` (which ats's board
fetchers call), so these are deterministic and offline.
"""
import os
import tempfile

from jobscope.apply import scout
from jobscope.core.config import load_config
from jobscope.core.model import Resume
from jobscope.core.store import Store
from jobscope.ingest import ats


def _cfg(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
    return cfg


def _resume() -> Resume:
    return Resume(full_name="Mohit", location="Bengaluru, India",
                  skills=["python", "application security", "detection", "aws"],
                  titles=["Security Engineer"], seniority="junior", years_experience=2.0)


def _gh_board(*titles):
    """A Greenhouse-shaped payload with the given job titles."""
    return {"jobs": [
        {"title": t, "location": {"name": "Remote"}, "absolute_url": f"https://x/{i}",
         "content": "Security role. Python, AWS, detection engineering.", "updated_at": "2026-07-01"}
        for i, t in enumerate(titles)]}


def test_resolve_board_known_map_needs_no_network(monkeypatch):
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        return None

    monkeypatch.setattr(ats.httpx, "get_json", _boom)
    assert ats.resolve_board("Rubrik") == ("Rubrik", "greenhouse", "rubrik")
    assert calls["n"] == 0                                   # curated slug -> no fetch


def test_resolve_board_explicit_and_override():
    assert ats.resolve_board("Acme", provider="lever", slug="acme") == ("Acme", "lever", "acme")
    assert ats.resolve_board("Acme|ashby|acmeslug") == ("Acme", "ashby", "acmeslug")


def test_resolve_board_probe_picks_provider_with_jobs(monkeypatch):
    def _get_json(url, params=None):
        if "lever.co" in url:
            return [{"text": "Engineer", "categories": {"location": "Remote"},
                     "hostedUrl": "https://l/1", "descriptionPlain": "x", "createdAt": 0}]
        return {"jobs": []}                                  # greenhouse empty -> probe moves on

    monkeypatch.setattr(ats.httpx, "get_json", _get_json)
    resolved = ats.resolve_board("Zzznewco")                 # not in COMPANY_BOARDS
    assert resolved is not None and resolved[1] == "lever"


def test_resolve_board_none_when_no_board(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_json", lambda *a, **k: None)
    assert ats.resolve_board("Zzznope") is None


def test_scout_scores_and_ranks(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        store.save_resume(_resume(), name="research")
        monkeypatch.setattr(ats.httpx, "get_json",
                            lambda *a, **k: _gh_board("Application Security Engineer", "Sales Manager"))
        res = scout.scout(cfg, store, "Rubrik", save=False, limit=10)
        assert res["ok"] and res["provider"] == "greenhouse"
        assert res["count"] == 2 and len(res["results"]) == 2
        # the security role outranks the sales role
        assert "security" in res["results"][0]["title"].lower()
        store.close()


def test_scout_save_upserts_matches(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        store.save_resume(_resume(), name="research")
        monkeypatch.setattr(ats.httpx, "get_json",
                            lambda *a, **k: _gh_board("Application Security Engineer"))
        res = scout.scout(cfg, store, "Rubrik", save=True, limit=10)
        assert res["ok"]
        # if it matched the profile, saving upserted it into the store
        if res["matched"]:
            assert res["saved"] >= 1 and len(store.jobs()) >= 1
        store.close()


def test_scout_no_resume_errors(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        monkeypatch.setattr(ats.httpx, "get_json", lambda *a, **k: _gh_board("Security Engineer"))
        res = scout.scout(cfg, store, "Rubrik")
        assert not res["ok"] and "resume import" in res["error"]
        store.close()


def test_scout_unknown_company_needs_slug(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        store.save_resume(_resume(), name="research")
        monkeypatch.setattr(ats.httpx, "get_json", lambda *a, **k: None)   # no board anywhere
        res = scout.scout(cfg, store, "Zzznope")
        assert not res["ok"] and res.get("needs_slug")
        store.close()
