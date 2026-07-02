"""Tests for the multi-profile scraper (JobSpy is mocked; no network, no pandas)."""
import os
import sys
import tempfile
import types

from jobscope import scrape
from jobscope.config import load_config
from jobscope.model import derive_remote_scope
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


def test_derive_remote_corroborates_flag():
    # JobSpy over-reports remote: a concrete city + no remote keyword must NOT be remote.
    assert scrape._derive_remote(True, "Dublin, County Dublin, Ireland", "Security Engineer") is False
    assert scrape._derive_remote(True, "Bengaluru, Karnataka, India", "Detection Engineer") is False
    # explicit remote wording wins, even if the flag was False
    assert scrape._derive_remote(False, "Remote - India", "X") is True
    assert scrape._derive_remote(False, "", "Remote Security Engineer") is True
    # a bare remote flag with no concrete place is trusted
    assert scrape._derive_remote(True, "United States", "X") is True
    assert scrape._derive_remote(True, "", "X") is True
    # not remote by default
    assert scrape._derive_remote(False, "Pune, India", "X") is False


def test_derive_remote_scope_classifies_region_vs_global():
    # a qualifier after "remote" is captured and normalized
    assert derive_remote_scope("Remote in Ireland", "", True) == "Ireland"
    assert derive_remote_scope("Remote - India", "", True) == "India"
    assert derive_remote_scope("Remote, IN", "", True) == "India"
    assert derive_remote_scope("Remote (US)", "", True) == "United States"
    # a concrete place carried on the title-driven remote flag -> its country
    assert derive_remote_scope("Dublin, County Dublin, Ireland", "Remote SecEng", True) == "Ireland"
    # bare remote with no qualifier or place -> global
    assert derive_remote_scope("Remote", "", True) == "global"
    # not remote -> no scope
    assert derive_remote_scope("Dublin, County Dublin, Ireland", "Security Engineer", False) == ""


def test_derive_remote_scope_rejects_noise():
    # "in" is word-anchored: "India" must not be read as "in" + "dia"
    assert derive_remote_scope("Remote India", "", True) == "global"
    assert derive_remote_scope("Remote Indiana", "", True) == "global"
    # the title is never parsed, so job-title words can't leak into the scope
    assert derive_remote_scope("Remote,", "Security Engineer II", True) == "global"
    # work-mode words are stripped rather than becoming a fake region
    assert derive_remote_scope("Remote-first", "", True) == "global"
    assert derive_remote_scope("US - Remote", "", True) == "global"
    # a trailing "-remote" on a real place is cleaned back to the place
    assert derive_remote_scope("Bengaluru, US-Remote", "", True) == "United States"
    # multi-region tokens normalize each side
    assert derive_remote_scope("Remote - US/Canada", "", True) == "United States/Canada"


def test_row_to_job_sets_scope_and_raw_flag():
    geo = scrape._row_to_job({
        "site": "linkedin", "title": "Detection Engineer", "company": "Acme",
        "location": "Remote - India", "is_remote": True, "job_url": "https://x/1",
    })
    assert geo.is_remote is True
    assert geo.remote_scope == "India"
    assert geo.raw_is_remote is True
    glob = scrape._row_to_job({
        "site": "linkedin", "title": "SWE", "company": "Acme",
        "location": "Remote", "is_remote": True, "job_url": "https://x/2",
    })
    assert glob.remote_scope == "global"
    assert glob.raw_is_remote is True
