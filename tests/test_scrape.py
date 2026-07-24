"""Tests for the multi-profile scraper (JobSpy is mocked; no network, no pandas)."""
import json
import os
import sys
import tempfile
import types

from jobscope.ingest import scrape
from jobscope.core.config import load_config
from jobscope.core.model import derive_remote_scope
from jobscope.core.store import Store, now_iso


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
    cfg["search"]["companies"] = []
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
            cfg = _cfg(tmp, sites=["linkedin"], terms=["security engineer", "detection engineer"], profiles=[
                {"name": "remote", "location": "Remote", "hours_old": 168},
                {"name": "india-onsite", "location": "India", "is_remote": False, "hours_old": 720},
            ])
            store = Store(cfg["output"]["db_path"])
            rc = scrape.run(cfg, store)
            assert rc == 0
            # 2 terms x 2 profiles = 4 searches
            assert len(calls) == 4
            assert {c["location"] for c in calls} == {"Remote", "India"}
            assert {c["results_wanted"] for c in calls} == {10}
            assert {c["offset"] for c in calls} == {0}
            assert {c["description_format"] for c in calls} == {"html"}
            # the on-site Pune role (excluded by the old remote-only scan) is now captured
            jobs = store.jobs()
            assert any("pune" in (j.location or "").lower() and not j.is_remote for j in jobs)
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_scopes_each_preferred_job_market_independently():
    calls = []

    def rows_for(kwargs):
        return [{
            "site": "indeed", "title": "Security Engineer", "company": "Acme",
            "location": "Berlin, Germany", "job_url": "https://example.test/de",
            "is_remote": False,
        }]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["indeed"], terms=["security"], results_wanted=1,
                home_country="India", scope_to_home=True,
                profiles=[{
                    "name": "Germany", "location": "Germany",
                    "home_country": "Germany", "country_indeed": "Germany",
                }],
            )
            store = Store(cfg["output"]["db_path"])

            assert scrape.run(cfg, store) == 0

            assert calls[0]["location"] == "Germany"
            assert calls[0]["country_indeed"] == "Germany"
            assert [job.location for job in store.jobs()] == ["Berlin, Germany"]
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_excludes_remote_rows_when_profile_disables_remote():
    from jobscope.analyze import profile

    calls = []

    def rows_for(_kwargs):
        return [
            {
                "site": "indeed", "title": "Security Engineer", "company": "Local",
                "location": "Berlin, Germany", "job_url": "https://example.test/local",
                "is_remote": False,
            },
            {
                "site": "indeed", "title": "Security Engineer", "company": "Remote",
                "location": "Remote", "job_url": "https://example.test/remote",
                "is_remote": True,
            },
        ]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["indeed"], terms=["security"], results_wanted=2,
                home_country="India", scope_to_home=True,
            )
            profile.write_profile(profile._profile_file(cfg, "research"), {
                "resume": "research", "search_terms": ["Security Engineer"],
                "locations": ["Germany"], "remote": False,
            })
            profile._write_active(cfg, "research")
            with Store(cfg["output"]["db_path"]) as store:
                assert scrape.run(cfg, store) == 0
                assert [job.location for job in store.jobs()] == ["Berlin, Germany"]
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_backward_compatible_without_profiles():
    calls = []
    _install_fake_jobspy(calls, lambda kw: [])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, sites=["indeed"], terms=["x"], profiles=[])
            store = Store(cfg["output"]["db_path"])
            scrape.run(cfg, store)
            assert len(calls) == 1                       # single search from the base
            assert calls[0]["location"] == cfg["search"]["location"]
            health = store.source_health("jobspy:indeed:Remote:x")[0]
            assert health["status"] == "empty" and health["item_count"] == 0
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_records_saturated_result_cap():
    calls = []

    def rows_for(_kwargs):
        return [
            {
                "site": "linkedin", "title": f"Security Engineer {index}",
                "company": "Acme", "location": "Remote",
                "job_url": f"https://example.test/{index}", "is_remote": True,
            }
            for index in range(2)
        ]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp, sites=["linkedin"], terms=["security"], profiles=[], results_wanted=2)
            store = Store(cfg["output"]["db_path"])

            scrape.run(cfg, store)

            assert calls[0]["results_wanted"] == 2
            assert calls[0]["offset"] == 0
            health = store.source_health("jobspy:linkedin:Remote:security")[0]
            assert health["status"] == "saturated" and health["item_count"] == 2
            assert "additional results may exist" in health["detail"]
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_resumes_in_bounded_pages_and_completes_at_configured_cap():
    calls = []

    def rows_for(kwargs):
        offset = kwargs["offset"]
        return [{
            "site": kwargs["site_name"], "title": f"Security Engineer {index}",
            "company": "Acme", "location": "Remote",
            "job_url": f"https://example.test/{index}", "is_remote": True,
        } for index in range(offset, offset + kwargs["results_wanted"])]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["indeed"], terms=["security"], profiles=[],
                results_wanted=25,
            )
            store = Store(cfg["output"]["db_path"])

            assert scrape.run(cfg, store) == 0
            assert len(store.jobs()) == 10
            assert store.meta_get(scrape.DISCOVERY_MARKER) is None
            assert scrape.discovery_due(cfg, store)

            assert scrape.run(cfg, store) == 0
            assert len(store.jobs()) == 20
            assert store.meta_get(scrape.DISCOVERY_MARKER) is None

            assert scrape.run(cfg, store) == 0
            assert len(store.jobs()) == 25
            assert store.meta_get(scrape.DISCOVERY_MARKER)
            assert json.loads(store.meta_get(scrape.DISCOVERY_CURSOR_MARKER) or "{}") == {}
            assert [call["offset"] for call in calls] == [0, 10, 20]
            assert [call["results_wanted"] for call in calls] == [10, 10, 5]
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_tracks_completion_independently_per_source():
    calls = []

    def rows_for(kwargs):
        count = 3 if kwargs["site_name"] == "indeed" else kwargs["results_wanted"]
        return [{
            "site": kwargs["site_name"],
            "title": f"{kwargs['site_name']} Engineer {kwargs['offset'] + index}",
            "company": "Acme", "location": "Remote",
            "job_url": f"https://{kwargs['site_name']}.test/{kwargs['offset'] + index}",
            "is_remote": True,
        } for index in range(count)]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["indeed", "linkedin"], terms=["security"],
                profiles=[], results_wanted=20,
            )
            store = Store(cfg["output"]["db_path"])

            scrape.run(cfg, store)
            scrape.run(cfg, store)

            assert [(call["site_name"], call["offset"]) for call in calls] == [
                ("indeed", 0), ("linkedin", 0), ("linkedin", 10),
            ]
            assert len(store.jobs()) == 23
            assert store.meta_get(scrape.DISCOVERY_MARKER)
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_retries_the_same_page_after_an_error():
    calls = []

    def rows_for(kwargs):
        if len(calls) == 2:
            raise RuntimeError("temporary rate limit")
        count = kwargs["results_wanted"] if kwargs["offset"] == 0 else 1
        return [{
            "site": "linkedin", "title": f"Engineer {kwargs['offset'] + index}",
            "company": "Acme", "location": "Remote",
            "job_url": f"https://example.test/{kwargs['offset'] + index}",
            "is_remote": True,
        } for index in range(count)]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["linkedin"], terms=["security"], profiles=[],
                results_wanted=25,
            )
            store = Store(cfg["output"]["db_path"])

            scrape.run(cfg, store)
            scrape.run(cfg, store)
            scrape.run(cfg, store)

            assert [call["offset"] for call in calls] == [0, 10, 10]
            assert len(store.jobs()) == 11
            assert store.meta_get(scrape.DISCOVERY_MARKER)
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_scrape_deduplicates_stable_job_ids_across_pages():
    calls = []

    def rows_for(kwargs):
        return [{
            "site": "linkedin", "title": f"Engineer {index}",
            "company": "Acme", "location": "Remote",
            "job_url": f"https://example.test/{index}", "is_remote": True,
        } for index in range(kwargs["results_wanted"])]

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["linkedin"], terms=["security"], profiles=[],
                results_wanted=20,
            )
            store = Store(cfg["output"]["db_path"])

            scrape.run(cfg, store)
            scrape.run(cfg, store)

            assert [call["offset"] for call in calls] == [0, 10]
            assert len(store.jobs()) == 10
            assert store.meta_get(scrape.DISCOVERY_MARKER)
            store.close()
    finally:
        sys.modules.pop("jobspy", None)


def test_forced_first_page_error_stays_due_during_cooldown():
    calls = []

    def rows_for(_kwargs):
        raise RuntimeError("temporary rate limit")

    _install_fake_jobspy(calls, rows_for)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(
                tmp, sites=["linkedin"], terms=["security"], profiles=[],
                results_wanted=20,
            )
            store = Store(cfg["output"]["db_path"])
            try:
                store.meta_set(scrape.DISCOVERY_MARKER, now_iso())

                scrape.run(cfg, store, force_discovery=True)

                cursors = json.loads(store.meta_get(scrape.DISCOVERY_CURSOR_MARKER) or "{}")
                assert list(cursors.values()) == [0]
                assert scrape.discovery_due(cfg, store)
            finally:
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


def test_row_to_job_strips_untrusted_description_html():
    job = scrape._row_to_job({
        "site": "indeed", "title": "Security Engineer", "company": "Acme",
        "location": "Remote", "is_remote": True, "job_url": "https://x/3",
        "description": "<style>body{display:none}</style><p>Detect &amp; respond</p>"
                       "<script>steal()</script>",
    })

    assert job.description == "Detect & respond"
