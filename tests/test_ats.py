"""Tests for ATS-direct company board fetching (HTTP is mocked; no network)."""
import os
import tempfile

from jobscope import ats
from jobscope.config import load_config
from jobscope.store import Store


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


def test_greenhouse_run_filters_by_location_and_role(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
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


def test_description_html_is_stripped_and_unescaped(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
    jobs = ats.fetch_company("Databricks", "greenhouse", "databricks")
    ir = next(j for j in jobs if j.title.startswith("Senior Security"))
    assert ir.description == "Detect & respond to threats."
    assert ir.date_posted == "2026-06-30"
    assert ir.source == "ats"


def test_lever_remote_kept_even_when_city_named(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
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
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
    jobs = ats.fetch_company("Acme", "ashby", "acme")
    assert len(jobs) == 1
    assert jobs[0].is_remote is True
    assert jobs[0].title == "Product Security Engineer"


def test_unknown_company_is_skipped(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, companies=["totally-unknown-co"])
        store = Store(cfg["output"]["db_path"])
        assert ats.run(cfg, store) == 0
        store.close()


def test_no_companies_is_noop(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, companies=[])
        store = Store(cfg["output"]["db_path"])
        assert ats.run(cfg, store) == 0
        store.close()


def test_matches_unit():
    from jobscope.model import Job
    locs, roles = {"india"}, {"security engineer"}
    india = Job(title="Security Engineer", location="Bengaluru, India")
    remote = Job(title="Security Engineer", location="Remote - US", is_remote=True)
    uk = Job(title="Security Engineer", location="London, UK")
    sales = Job(title="Account Executive", location="Bengaluru, India")
    assert ats._matches(india, locs, roles, want_remote=True) is True
    assert ats._matches(remote, locs, roles, want_remote=True) is True
    assert ats._matches(remote, locs, roles, want_remote=False) is False
    assert ats._matches(uk, locs, roles, want_remote=True) is False
    assert ats._matches(sales, locs, roles, want_remote=True) is False


_BOARD2 = {"jobs": [
    {"title": "Security Engineer", "location": {"name": "Bengaluru, India"},
     "absolute_url": "https://gh/db/1", "content": "x", "updated_at": "2026-06-30T00:00:00-04:00"},
    {"title": "Detection Engineer", "location": {"name": "Remote - India"},
     "absolute_url": "https://gh/db/2", "content": "x", "updated_at": "2026-06-30T00:00:00-04:00"},
]}


def test_taken_down_when_missing_from_board(monkeypatch):
    state = {"data": {"jobs": list(_BOARD2["jobs"])}}
    monkeypatch.setattr(ats.httpx, "get_json",
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
    monkeypatch.setattr(ats.httpx, "get_json",
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
    from jobscope.model import Job
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
    monkeypatch.setattr(ats.httpx, "get_json", _fake_get_json)
    jobs = ats.fetch_company("Acme", "ashby", "acme")        # location "Remote - India", isRemote
    assert jobs[0].remote_scope == "India"
    assert jobs[0].raw_is_remote is None
