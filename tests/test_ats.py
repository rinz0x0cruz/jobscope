"""Tests for ATS-direct company board fetching (HTTP is mocked; no network)."""
import os
import tempfile

import pytest

from jobscope.ingest import ats
from jobscope.core.config import load_config
from jobscope.core.model import Job
from jobscope.core.store import Store


GREENHOUSE = {
    "jobs": [
        {"title": "Senior Security Engineer, Incident Response",
         "location": {"name": "Bengaluru, India"},
         "absolute_url": "https://boards.greenhouse.io/databricks/jobs/1",
         "content": "<p>Detect &amp; respond to threats.</p>",
         "updated_at": "2026-06-30T10:00:00-04:00"},
        {"title": "Staff Detection Engineer",
         "location": {"name": "Remote - India"},
         "absolute_url": "https://boards.greenhouse.io/databricks/jobs/2",
         "content": "Build detections", "updated_at": "2026-06-29T10:00:00-04:00"},
        {"title": "Enterprise Account Executive",       # role filtered out
         "location": {"name": "Bengaluru, India"},
         "absolute_url": "https://boards.greenhouse.io/databricks/jobs/3",
         "content": "Sell", "updated_at": "2026-06-28T10:00:00-04:00"},
        {"title": "Security Engineer",                   # location filtered out (UK, on-site)
         "location": {"name": "London, UK"},
         "absolute_url": "https://boards.greenhouse.io/databricks/jobs/4",
         "content": "eu role", "updated_at": "2026-06-28T10:00:00-04:00"},
    ]
}

LEVER = [
    {"text": "Application Security Engineer",
     "categories": {"location": "Toronto"}, "workplaceType": "remote",
     "hostedUrl": "https://jobs.lever.co/acme/1", "descriptionPlain": "appsec role",
     "createdAt": 1719705600000},
]

ASHBY = {
    "jobs": [
        {"title": "Product Security Engineer", "location": "Remote - India",
         "jobUrl": "https://jobs.ashbyhq.com/acme/2",
         "descriptionHtml": "<p>appsec</p>", "isRemote": True},
    ]
}

def _fake_get_json(url, **_kw):
    if "greenhouse" in url:
        return GREENHOUSE
    if "lever" in url:
        return LEVER
    if "ashby" in url:
        return ASHBY
    return None


def _patch_json(monkeypatch, fetch=_fake_get_json):
    def get_json_result(url, **kwargs):
        data = fetch(url, **kwargs)
        return ats.httpx.HttpResult(
            ok=data is not None,
            status_code=200 if data is not None else None,
            attempts=1,
            data=data,
            error="mock request failed" if data is None else "",
        )

    monkeypatch.setattr(ats.httpx, "get_json_result", get_json_result)


def _cfg(tmp, **search_over):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "s.db")
    cfg["search"].update(search_over)
    return cfg


def test_resolve_known_and_explicit_override():
    assert ats._resolve("databricks") == ("databricks", "greenhouse", "databricks")
    assert ats._resolve("Acme|lever|acme-co") == ("Acme", "lever", "acme-co")
    assert ats._resolve("Acme:ashby:acme") == ("Acme", "ashby", "acme")
    assert ats._resolve("totally-unknown-co") is None
    assert ats._resolve("NTT DATA") is None
    assert ats.board_url("phenom", "NTT1GLOBAL") == ""


def test_greenhouse_board_filters_by_location_and_role(monkeypatch):
    _patch_json(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, terms=["security engineer", "detection engineer"],
                   country_indeed="India", is_remote=True)
        with Store(cfg["output"]["db_path"]) as store:
            board = ats.fetch_company("Databricks", "greenhouse", "databricks")
            kept = ats.filter_profile_jobs(cfg, store, board)
    # kept: India security-engineer + remote-India detection-engineer
    assert {job.title for job in kept} == {
        "Senior Security Engineer, Incident Response", "Staff Detection Engineer",
    }


def test_board_filter_targets_threat_hunter_without_generic_engineering_roles():
    cfg = load_config(None)
    cfg["search"].update({
        "terms": ["Security Engineer"],
        "scope_to_home": False,
        "location": "Remote",
        "is_remote": True,
    })
    jobs = [
        Job(title="Senior Threat Hunter", location="Remote", is_remote=True),
        Job(title="SOC Engineer - L2", location="Remote", is_remote=True),
        Job(title="Associate Information Security Analyst", location="Remote", is_remote=True),
        Job(title="Application-Security-Engineer", location="Remote", is_remote=True),
        Job(title="Manager, Software Engineering", location="Remote", is_remote=True),
        Job(title="Social Media Manager", location="Remote", is_remote=True),
        Job(title="Engineering Manager - Backend", location="Remote", is_remote=True),
    ]

    kept = ats.filter_board_jobs(cfg, jobs)

    assert [job.title for job in kept] == [
        "Senior Threat Hunter",
        "SOC Engineer - L2",
        "Associate Information Security Analyst",
        "Application-Security-Engineer",
    ]


def test_description_html_is_stripped_and_unescaped(monkeypatch):
    _patch_json(monkeypatch)
    jobs = ats.fetch_company("Databricks", "greenhouse", "databricks")
    ir = next(j for j in jobs if j.title.startswith("Senior Security"))
    assert ir.description == "Detect & respond to threats."
    assert ir.date_posted == "2026-06-30"
    assert ir.source == "ats"


def test_lever_remote_kept_even_when_city_named(monkeypatch):
    _patch_json(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, terms=["application security engineer"],
                   country_indeed="India", is_remote=True)
        with Store(cfg["output"]["db_path"]) as store:
            kept = ats.filter_profile_jobs(
                cfg, store, ats.fetch_company("Acme", "lever", "acme"),
            )
    assert len(kept) == 1
    assert kept[0].is_remote is True                     # workplaceType=remote wins over "Toronto"
    assert kept[0].date_posted == "2024-06-30"           # 1719705600000 ms -> 2024-06-30 UTC


def test_ashby_remote_flag(monkeypatch):
    _patch_json(monkeypatch)
    jobs = ats.fetch_company("Acme", "ashby", "acme")
    assert len(jobs) == 1
    assert jobs[0].is_remote is True
    assert jobs[0].title == "Product Security Engineer"


def test_board_fetch_result_distinguishes_empty_error_and_invalid(monkeypatch):
    _patch_json(monkeypatch, lambda *_a, **_k: {"jobs": []})
    empty = ats.fetch_company_result("Acme", "greenhouse", "acme")
    assert empty.status == ats.BoardStatus.EMPTY
    assert empty.successful and empty.jobs == []

    _patch_json(monkeypatch, lambda *_a, **_k: None)
    failed = ats.fetch_company_result("Acme", "greenhouse", "acme")
    assert failed.status == ats.BoardStatus.ERROR
    assert not failed.successful and "mock request failed after 1 attempt" in failed.detail

    _patch_json(monkeypatch, lambda *_a, **_k: {"unexpected": []})
    invalid = ats.fetch_company_result("Acme", "greenhouse", "acme")
    assert invalid.status == ats.BoardStatus.INVALID
    assert not invalid.successful and "jobs list" in invalid.detail


def test_board_fetch_result_preserves_partial_jobs(monkeypatch):
    _patch_json(
        monkeypatch,
        lambda *_a, **_k: {"jobs": [GREENHOUSE["jobs"][0], "malformed"]},
    )

    result = ats.fetch_company_result("Acme", "greenhouse", "acme")

    assert result.status == ats.BoardStatus.PARTIAL
    assert result.successful and len(result.jobs) == 1
    assert result.detail == "1 malformed posting(s)"


def test_board_fetch_result_rejects_unsupported_provider():
    result = ats.fetch_company_result("Acme", "workday", "acme")

    assert result.status == ats.BoardStatus.UNSUPPORTED
    assert not result.successful and result.jobs == []


def test_unreviewed_source_host_is_blocked_before_http(monkeypatch):
    monkeypatch.setattr(
        ats.httpx, "get_json_result",
        lambda *_args, **_kwargs: pytest.fail("unreviewed host reached HTTP client"),
    )

    data, error, attempts, status_code = ats._load_json(
        "https://greenhouse.example.test/v1/boards/acme/jobs",
        params={}, provider="greenhouse",
    )

    assert data is None
    assert error == "blocked unreviewed greenhouse source host"
    assert attempts == 0 and status_code is None


def test_phenom_is_quarantined_without_request(monkeypatch):
    monkeypatch.setattr(
        ats.httpx, "get_json_result",
        lambda *_args, **_kwargs: pytest.fail("quarantined provider reached HTTP client"),
    )

    result = ats.fetch_company_result("NTT DATA", "phenom", "NTT1GLOBAL")

    assert result.status == ats.BoardStatus.UNSUPPORTED
    assert not result.successful and result.jobs == []


def test_matches_unit():
    from jobscope.core.model import Job, derive_remote_scope

    def mk(title, loc, is_remote=False):
        j = Job(title=title, location=loc, is_remote=is_remote)
        j.remote_scope = derive_remote_scope(loc, title, is_remote)
        return j

    locs, roles = {"india"}, {"security engineer"}
    india = mk("Security Engineer", "Bengaluru, India")
    remote_us = mk("Security Engineer", "Remote - US", is_remote=True)
    remote_global = mk("Security Engineer", "Remote", is_remote=True)
    remote_india = mk("Security Engineer", "Remote - India", is_remote=True)
    uk = mk("Security Engineer", "London, UK")
    sales = mk("Account Executive", "Bengaluru, India")
    # in scope: India onsite, global remote, India remote
    assert ats._matches(india, locs, roles, want_remote=True) is True
    assert ats._matches(remote_global, locs, roles, want_remote=True) is True
    assert ats._matches(remote_india, locs, roles, want_remote=True) is True
    # out of scope: remote locked to another country, foreign onsite, wrong role
    assert ats._matches(remote_us, locs, roles, want_remote=True) is False
    assert ats._matches(uk, locs, roles, want_remote=True) is False
    assert ats._matches(sales, locs, roles, want_remote=True) is False
    assert ats._matches(remote_global, locs, roles, want_remote=False) is False
    # geo_on=False falls back to the legacy location match (want_remote honored)
    assert ats._matches(remote_us, locs, roles, want_remote=True, geo_on=False) is True
    assert ats._matches(remote_us, locs, roles, want_remote=False, geo_on=False) is False


def test_profile_filter_honors_preferred_market_and_work_mode():
    from jobscope.analyze import profile

    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, home_country="India", scope_to_home=True)
        path = profile._profile_file(cfg, "research")
        base = {
            "resume": "research", "search_terms": ["Security Engineer"],
            "locations": ["Germany"], "remote": False,
        }
        profile.write_profile(path, base)
        profile._write_active(cfg, "research")
        jobs = [
            Job(id="de", title="Security Engineer", company="A", location="Berlin, Germany"),
            Job(id="in", title="Security Engineer", company="B", location="Pune, India"),
            Job(
                id="remote", title="Security Engineer", company="C", location="Remote",
                is_remote=True, remote_scope="global",
            ),
        ]
        with Store(cfg["output"]["db_path"]) as store:
            kept, funnel = ats.filter_profile_jobs_with_funnel(cfg, store, jobs)
            assert [job.id for job in kept] == ["de"]
            assert funnel["geo_eligible"] == 1

            profile.write_profile(path, {**base, "locations": [], "remote": True})
            kept, funnel = ats.filter_profile_jobs_with_funnel(cfg, store, jobs)
            assert [job.id for job in kept] == ["remote"]
            assert funnel["geo_eligible"] == 1


def test_reopen_on_reappearance():
    """A re-listed posting comes back as open. Taken-down detection itself is
    covered on the live path in tests/test_monitor_scan.py."""
    from jobscope.core.model import Job
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        with Store(cfg["output"]["db_path"]) as store:
            job = Job(source="ats", title="SE", company="X", url="u1").ensure_id()
            still_listed = Job(source="ats", title="SE2", company="X", url="u2").ensure_id()
            store.upsert_job(job)
            store.upsert_job(still_listed)
            watch = store.upsert_company_monitor(
                "X", provider="greenhouse", slug="x", added_from="user",
            )
            store.link_monitor_job(watch["id"], job.id)
            assert store.reconcile_monitor_jobs(watch["id"], {still_listed.id}) == 1
            assert store.get_job(job.id).status == "closed"
            store.upsert_job(job)                            # reappears -> reopened
            assert store.get_job(job.id).status == "open"
            assert store.get_job(job.id).closed_at == ""
        store.close()


def test_mk_sets_remote_scope_and_leaves_raw_flag_none():
    geo = ats._mk("Acme", "Detection Engineer", "Remote - India",
                  "https://x/1", "desc", "2026-06-30")
    assert geo.is_remote is True
    assert geo.remote_scope == "India"
    assert geo.raw_is_remote is None                         # never from JobSpy on ATS
    glob = ats._mk("Acme", "SWE", "Remote", "https://x/2", "d", "2026-06-30")
    assert glob.is_remote is True and glob.remote_scope == "global"
    assert glob.raw_is_remote is None


def test_ashby_provider_derives_remote_scope(monkeypatch):
    _patch_json(monkeypatch)
    jobs = ats.fetch_company("Acme", "ashby", "acme")        # location "Remote - India", isRemote
    assert jobs[0].remote_scope == "India"
    assert jobs[0].raw_is_remote is None
