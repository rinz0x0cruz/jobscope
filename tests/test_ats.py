"""Tests for ATS-direct company board fetching (HTTP is mocked; no network)."""
import json
import os
import tempfile
import threading
import time

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

PHENOM = {
    "refineSearch": {
        "status": 200,
        "hits": 2,
        "totalHits": 2,
        "data": {"jobs": [
            {
                "jobId": "P-100131",
                "title": "SASE ENGINEER",
                "location": "Noida, India",
                "multi_location": ["Noida, India", "Bengaluru, India"],
                "postedDate": "2026-07-01T00:00:00.000+0000",
                "descriptionTeaser": "Security platform engineering",
                "ml_job_parser": {"descriptionTeaser_ats": "SIEM and SASE operations"},
            },
            {
                "jobId": "P-100130",
                "title": "Platform Support Engineer L2",
                "location": "Bengaluru, India",
                "multi_location": [],
                "postedDate": "2026-06-30T00:00:00.000+0000",
                "descriptionTeaser": "SIEM platform support",
            },
        ]},
    },
}


def _fake_get_json(url, **_kw):
    if "greenhouse" in url:
        return GREENHOUSE
    if "lever" in url:
        return LEVER
    if "ashby" in url:
        return ASHBY
    if "phenompeople" in url:
        return PHENOM
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
    assert ats._resolve("NTT DATA") == ("NTT DATA", "phenom", "NTT1GLOBAL")
    assert ats.board_url("phenom", "NTT1GLOBAL") == (
        "https://careers.services.global.ntt/global/en/search-results"
    )


def test_greenhouse_run_filters_by_location_and_role(monkeypatch):
    _patch_json(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, terms=["security engineer", "detection engineer"],
                   country_indeed="India", is_remote=True, companies=["databricks"])
        store = Store(cfg["output"]["db_path"])
        new = ats.run(cfg, store)
        titles = {j.title for j in store.jobs()}
        store.close()
    # kept: India security-engineer + remote-India detection-engineer
    assert new == 2
    assert titles == {"Senior Security Engineer, Incident Response", "Staff Detection Engineer"}


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
                   country_indeed="India", is_remote=True, companies=["Acme|lever|acme"])
        store = Store(cfg["output"]["db_path"])
        new = ats.run(cfg, store)
        jobs = store.jobs()
        store.close()
    assert new == 1
    assert jobs[0].is_remote is True                     # workplaceType=remote wins over "Toronto"
    assert jobs[0].date_posted == "2024-06-30"           # 1719705600000 ms -> 2024-06-30 UTC


def test_ashby_remote_flag(monkeypatch):
    _patch_json(monkeypatch)
    jobs = ats.fetch_company("Acme", "ashby", "acme")
    assert len(jobs) == 1
    assert jobs[0].is_remote is True
    assert jobs[0].title == "Product Security Engineer"


def test_phenom_fetches_bounded_category_and_normalizes_jobs(monkeypatch):
    calls = []

    def fetch(url, **kwargs):
        calls.append((url, kwargs["params"]))
        return PHENOM

    _patch_json(monkeypatch, fetch)
    result = ats.fetch_company_result("NTT DATA", "phenom", "NTT1GLOBAL")

    assert result.status == ats.BoardStatus.OK and len(result.jobs) == 2
    assert result.attempts == 1 and len(calls) == 1
    assert json.loads(calls[0][1]["payload"])["selected_fields"] == {
        "category": ["Information Security"],
    }
    sase = next(job for job in result.jobs if job.title == "SASE ENGINEER")
    assert sase.location == "Noida, India | Bengaluru, India"
    assert sase.description == "SIEM and SASE operations"
    assert sase.date_posted == "2026-07-01"
    assert sase.url.endswith("/job/P-100131/SASE-ENGINEER")


def test_phenom_hydrates_full_description_after_filtering(monkeypatch):
    detail = {
        "jobDetail": {"data": {"job": {
            "description": "<p>Monitor SIEM alerts &amp; support incident response.</p>",
        }}},
    }
    html = f"<script>phApp.ddo = {json.dumps(detail)};</script>"
    monkeypatch.setattr(ats.httpx, "get_text_result", lambda *_a, **_k: (
        ats.httpx.HttpResult(True, 200, 1, html, "")
    ))
    job = Job(
        title="Associate Information Security Analyst",
        url="https://careers.services.global.ntt/global/en/job/R-1/role",
        description="short teaser",
    )

    hydrated = ats.hydrate_company_jobs("phenom", [job])

    assert hydrated[0].description == "Monitor SIEM alerts & support incident response."


def test_phenom_hydration_is_bounded_parallel_and_preserves_order(monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    def fetch(url, **_kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.04)
        with lock:
            active -= 1
        detail = {"jobDetail": {"data": {"job": {"description": f"<p>{url}</p>"}}}}
        return ats.httpx.HttpResult(
            True, 200, 1, f"<script>phApp.ddo = {json.dumps(detail)};</script>", "",
        )

    monkeypatch.setattr(ats.httpx, "get_text_result", fetch)
    jobs = [Job(title=f"Role {index}", url=f"https://example.test/{index}") for index in range(8)]
    stats = {}

    hydrated = ats.hydrate_company_jobs("phenom", jobs, stats=stats)

    assert peak == 4
    assert hydrated is jobs
    assert [job.title for job in hydrated] == [f"Role {index}" for index in range(8)]
    assert [job.description for job in hydrated] == [f"https://example.test/{index}" for index in range(8)]
    assert stats == {"attempted": 8, "hydrated": 8, "failed": 0}


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


def test_unknown_company_is_skipped(monkeypatch):
    _patch_json(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, companies=["totally-unknown-co"])
        store = Store(cfg["output"]["db_path"])
        assert ats.run(cfg, store) == 0
        store.close()


def test_no_companies_is_noop(monkeypatch):
    _patch_json(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, companies=[])
        store = Store(cfg["output"]["db_path"])
        assert ats.run(cfg, store) == 0
        store.close()


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
    # geo_on=False falls back to the legacy location match (want_remote honored)
    assert ats._matches(remote_us, locs, roles, want_remote=True, geo_on=False) is True


_BOARD2 = {"jobs": [
    {"title": "Security Engineer", "location": {"name": "Bengaluru, India"},
     "absolute_url": "https://gh/db/1", "content": "x", "updated_at": "2026-06-30T00:00:00-04:00"},
    {"title": "Detection Engineer", "location": {"name": "Remote - India"},
     "absolute_url": "https://gh/db/2", "content": "x", "updated_at": "2026-06-30T00:00:00-04:00"},
]}


def test_taken_down_when_missing_from_board(monkeypatch):
    state = {"data": {"jobs": list(_BOARD2["jobs"])}}
    _patch_json(monkeypatch,
                lambda url, **_k: state["data"] if "greenhouse" in url else None)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, terms=["security engineer", "detection engineer"],
                   country_indeed="India", is_remote=True, companies=["databricks"])
        store = Store(cfg["output"]["db_path"])
        ats.run(cfg, store)
        ids = {j.title: j.id for j in store.jobs()}
        assert len(ids) == 2
        state["data"] = {"jobs": _BOARD2["jobs"][:1]}        # "Detection Engineer" pulled
        ats.run(cfg, store)
        gone = store.get_job(ids["Detection Engineer"])
        assert gone.status == "closed" and gone.closed_at
        assert store.get_job(ids["Security Engineer"]).status == "open"
        store.close()


def test_failed_fetch_does_not_close(monkeypatch):
    state = {"data": {"jobs": _BOARD2["jobs"][:1]}}
    _patch_json(monkeypatch,
                lambda url, **_k: state["data"] if "greenhouse" in url else None)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, terms=["security engineer"], country_indeed="India",
                   is_remote=True, companies=["databricks"])
        store = Store(cfg["output"]["db_path"])
        ats.run(cfg, store)
        jid = store.jobs()[0].id
        state["data"] = None                                 # fetch failure -> empty board
        ats.run(cfg, store)
        assert store.get_job(jid).status == "open"           # not closed on a failed fetch
        store.close()


def test_reopen_on_reappearance():
    from jobscope.core.model import Job
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        store = Store(cfg["output"]["db_path"])
        job = Job(source="ats", title="SE", company="X", url="u1").ensure_id()
        store.upsert_job(job)
        assert store.reconcile_open("ats", "X", {"other"}) == 1
        assert store.get_job(job.id).status == "closed"
        store.upsert_job(job)                                # reappears -> reopened
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
