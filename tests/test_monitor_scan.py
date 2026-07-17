import os
import tempfile

from jobscope.core.config import load_config
from jobscope.core.httpx import HttpResult
from jobscope.core.model import Job, Resume
from jobscope.core.store import Store
from jobscope.ingest import ats, monitor


def _setup():
    directory = tempfile.mkdtemp()
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(directory, "scan.db")
    cfg["search"]["companies"] = []
    cfg["search"]["scope_to_home"] = False
    cfg["search"]["terms"] = ["security engineer"]
    cfg["apply"]["outreach"]["monitor_scan"]["enabled"] = False
    store = Store(cfg["output"]["db_path"])
    store.save_resume(Resume(
        full_name="Mohit", location="India", skills=["python", "aws", "security"],
        titles=["Security Engineer"], seniority="junior", years_experience=2,
    ), name="research")
    return cfg, store


def _job(title: str, url: str) -> Job:
    return Job(
        source="ats", title=title, company="Acme", location="Remote",
        is_remote=True, url=url, description="Python AWS security engineering",
    ).ensure_id()


def _fetch(status=ats.BoardStatus.OK, jobs=None, detail=""):
    return ats.BoardFetchResult(
        "Acme", "greenhouse", "acme", status, jobs or [], detail, attempts=1,
        status_code=200 if status in {ats.BoardStatus.OK, ats.BoardStatus.EMPTY} else 503,
    )


def test_supported_board_urls_and_official_page_discovery(monkeypatch):
    assert ats.parse_board_url("https://job-boards.greenhouse.io/acme/jobs/123") == ("greenhouse", "acme")
    assert ats.parse_board_url("https://jobs.lever.co/acme/123") == ("lever", "acme")
    assert ats.parse_board_url("https://jobs.ashbyhq.com/acme/123") == ("ashby", "acme")

    monkeypatch.setattr(ats.httpx, "get_text_result", lambda *_a, **_k: HttpResult(
        True, 200, 1, '<a href="https://jobs.lever.co/acme">Jobs</a>', "",
    ))
    resolution = ats.resolve_board_result(
        "Acme", careers_url="https://acme.example/careers", probe=False,
    )
    assert resolution.resolved and resolution.provider == "lever" and resolution.slug == "acme"


def test_unsupported_workday_url_is_explicit(monkeypatch):
    monkeypatch.setattr(ats.httpx, "get_text_result", lambda *_a, **_k: HttpResult(
        False, 404, 1, error="HTTP 404",
    ))
    result = ats.resolve_board_result(
        "Acme", careers_url="https://acme.wd5.myworkdayjobs.com/careers", probe=False,
    )
    assert result.status == ats.ResolutionStatus.UNSUPPORTED


def test_scan_monitor_scores_links_reviews_and_records_health(monkeypatch):
    cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(
        jobs=[_job("Security Engineer", "https://x/one"), _job("Sales Manager", "https://x/two")],
    ))

    result = monitor.scan_monitor(cfg, store, company)

    assert result["ok"] and result["board_count"] == 2 and result["matched"] >= 1
    reviews = store.list_job_reviews(state="pending")
    assert reviews and reviews[0]["origins"] == ["monitored"]
    assert reviews[0]["monitor_ids"] == [company["id"]]
    assert store.source_health(f"monitor:{company['id']}")[0]["status"] == "ok"
    assert store.get_job(reviews[0]["job_id"]).score > 0
    assert store.get_company_monitor(company["id"])["last_success_at"]
    store.close()


def test_scan_monitor_failure_and_empty_board_never_close_jobs(monkeypatch):
    cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    existing = _job("Security Engineer", "https://x/existing")
    store.upsert_job(existing)
    store.link_monitor_job(company["id"], existing.id)

    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(
        status=ats.BoardStatus.ERROR, detail="temporary failure",
    ))
    failed = monitor.scan_monitor(cfg, store, company)
    assert not failed["ok"] and store.get_job(existing.id).status == "open"

    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(
        status=ats.BoardStatus.EMPTY,
    ))
    empty = monitor.scan_monitor(cfg, store, company)
    assert empty["ok"] and empty["closed"] == 0
    assert store.get_job(existing.id).status == "open"
    store.close()


def test_complete_board_closes_a_missing_linked_job(monkeypatch):
    cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    current = _job("Security Engineer", "https://x/current")
    missing = _job("Security Engineer", "https://x/missing")
    for job in (current, missing):
        store.upsert_job(job)
        store.link_monitor_job(company["id"], job.id)
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(jobs=[current]))

    result = monitor.scan_monitor(cfg, store, company)

    assert result["ok"] and result["closed"] == 1
    assert store.get_job(current.id).status == "open"
    assert store.get_job(missing.id).status == "closed"
    store.close()


def test_scheduled_scan_skips_monitors_that_need_portal_setup(monkeypatch):
    cfg, store = _setup()
    store.upsert_company_monitor("Unknown Labs", added_from="application")
    called = []
    monkeypatch.setattr(monitor, "resolve_monitor", lambda *_a, **_k: called.append(True))

    result = monitor.scan_active_monitors(cfg, store)

    assert result["companies"] == 0
    assert result["needs_setup"] == 1
    assert result["unresolved"] == ["Unknown Labs"]
    assert called == []
    store.close()


def test_targeted_scan_pulls_and_persists_preferred_security_recruiter(monkeypatch):
    from jobscope.apply import outreach

    cfg, store = _setup()
    cfg["apply"]["outreach"]["monitor_scan"]["enabled"] = True
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(
        jobs=[_job("Security Engineer", "https://x/current")],
    ))
    monkeypatch.setattr(outreach, "discover_company_contacts", lambda *_a, **_k: (
        "acme.com",
        [
            {"email": "talent@acme.com", "confidence": "medium", "source": "apollo",
             "note": "Talent Acquisition Partner via Apollo"},
            {"email": "cyber@acme.com", "confidence": "medium", "source": "apollo",
             "note": "Cybersecurity Recruiter via Apollo"},
        ],
    ))

    result = monitor.scan_monitor(cfg, store, company, refresh_contacts=True)

    assert result["ok"] is True
    assert result["contact_status"] == "updated"
    assert result["recruiter"]["email"] == "cyber@acme.com"
    assert result["recruiter_count"] == 2
    stored = store.get_company_contacts("Acme")
    assert stored["contacts"][0]["email"] == "cyber@acme.com"
    store.close()


def test_recruiter_lookup_failure_never_breaks_job_scan(monkeypatch):
    from jobscope.apply import outreach

    cfg, store = _setup()
    cfg["apply"]["outreach"]["monitor_scan"]["enabled"] = True
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(
        jobs=[_job("Security Engineer", "https://x/current")],
    ))
    monkeypatch.setattr(
        outreach, "refresh_company_contacts",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("finder unavailable")),
    )

    result = monitor.scan_monitor(cfg, store, company, refresh_contacts=True)

    assert result["ok"] is True and result["matched"] == 1
    assert result["contact_status"] == "error"
    assert "finder unavailable" in result["contact_error"]
    store.close()


def test_jobs_only_scan_never_runs_recruiter_lookup(monkeypatch):
    from jobscope.apply import outreach

    cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    monkeypatch.setattr(ats, "fetch_company_result", lambda *_a, **_k: _fetch(
        jobs=[_job("Security Engineer", "https://x/current")],
    ))
    monkeypatch.setattr(
        outreach, "refresh_company_contacts",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("recruiter lookup ran")),
    )

    result = monitor.scan_monitor(cfg, store, company, include_contacts=False)

    assert result["ok"] is True and result["matched"] == 1
    assert result["contact_status"] == "not-run"
    assert result["recruiter_count"] == 0 and result["recruiter"] is None
    store.close()