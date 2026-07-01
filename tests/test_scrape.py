"""Tests for the multi-profile scraper (JobSpy is mocked; no network, no pandas)."""
import os
import sys
import tempfile
import types

from jobscope import scrape
from jobscope.config import load_config
from jobscope.store import Store


class _FakeDF:
    """Minimal stand-in for a JobSpy DataFrame (len + iterrows over dict rows)."""

    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def iterrows(self):
        for i, r in enumerate(self._rows):
            yield i, r


def _install_fake_jobspy(calls, rows_for):
    mod = types.ModuleType("jobspy")

    def scrape_jobs(**kwargs):
        calls.append(kwargs)
        return _FakeDF(rows_for(kwargs))

    mod.scrape_jobs = scrape_jobs
    sys.modules["jobspy"] = mod


def _cfg(tmp, **search_over):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "s.db")
    cfg["search"].update(search_over)
    return cfg


def test_scrape_runs_every_profile():
    calls = []

    def rows_for(kw):
        onsite = kw.get("location") == "India"
        term = kw["search_term"].replace(" ", "")
        return [{
            "site": "linkedin", "title": "Security Engineer III", "company": "CrowdStrike",
            "location": "Pune, Maharashtra, India" if onsite else "Remote, IN",
            "job_url": f"https://ex/{kw.get('location')}/{term}",
            "is_remote": not onsite, "date_posted": "2026-06-30",
        }]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, terms=["security engineer", "detection engineer"], profiles=[
                {"name": "remote", "location": "Remote", "hours_old": 168},
                {"name": "india-onsite", "location": "India", "is_remote": False, "hours_old": 720},
            ])
            store = Store(cfg["output"]["db_path"])
            rc = scrape.run(cfg, store)
            assert rc == 0
            # 2 terms x 2 profiles = 4 searches
            assert len(calls) == 4
            assert {c["location"] for c in calls} == {"Remote", "India"}
            # the on-site Pune role (excluded by the old remote-only scan) is now captured
            jobs = store.jobs()
            assert any("pune" in (j.location or "").lower() and not j.is_remote for j in jobs)
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_backward_compatible_without_profiles():
    calls = []
    _install_fake_jobspy(calls, lambda kw: [])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, terms=["x"], profiles=[])
            store = Store(cfg["output"]["db_path"])
            scrape.run(cfg, store)
            assert len(calls) == 1                       # single search from the base
            assert calls[0]["location"] == cfg["search"]["location"]
            store.close()
    finally:
        sys.modules.pop("jobspy", None)
