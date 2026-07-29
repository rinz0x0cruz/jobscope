import os
import tempfile

from jobscope.core.config import load_config
from jobscope.core.model import Application, Job
from jobscope.core.store import Store
from jobscope.ingest.monitor import SEED_MARKER, board_url, seed_monitors, suggest_boards


def _setup():
    directory = tempfile.mkdtemp()
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(directory, "seed.db")
    cfg["search"]["companies"] = ["databricks", "Acme|lever|acme"]
    return cfg, Store(cfg["output"]["db_path"])


def test_seed_imports_config_and_active_applications_without_network():
    cfg, store = _setup()
    applied = Job(source="inbox", title="Analyst", company="Unknown Labs", url="https://x/applied").ensure_id()
    legacy = Job(source="indeed", title="Security Engineer", company="Legacy Co", url="https://x/legacy").ensure_id()
    store.upsert_job(applied)
    store.upsert_job(legacy)
    store.update_score(applied.id, 70, "Good", "fit")
    store.update_score(legacy.id, 80, "Strong", "fit")
    store.set_application(Application(
        job_id=applied.id, status="applied", company="Unknown Labs", applied_at="2026-07-15",
    ))

    result = seed_monitors(cfg, store)

    assert result == {
        "seeded": True,
        "already_seeded": False,
        "configured": 2,
        "applications": 1,
        "archived_known": 0,
        "legacy_saved": 1,
        "total": 2,
    }
    databricks = store.get_company_monitor("databricks")
    assert databricks["provider"] == "greenhouse" and databricks["slug"] == "databricks"
    assert store.get_company_monitor("Unknown Labs") is None
    assert store.get_job_review(legacy.id)["state"] == "saved"
    assert store.get_job_review(applied.id) is None
    assert store.meta_get(SEED_MARKER) == "1"
    store.close()


def test_seed_archives_legacy_application_only_monitor_without_losing_links():
    cfg, store = _setup()
    job = Job(
        source="inbox", title="Analyst", company="Unknown Labs",
        url="https://x/application",
    ).ensure_id()
    store.upsert_job(job)
    store.set_application(Application(
        job_id=job.id, status="applied", company="Unknown Labs",
        applied_at="2026-07-15",
    ))
    legacy = store.upsert_company_monitor("Unknown Labs", added_from="application")
    store.link_monitor_job(legacy["id"], job.id)
    store.meta_set(SEED_MARKER, "1")

    result = seed_monitors(cfg, store)

    assert result["archived_known"] == 1
    assert result["already_seeded"] is True
    assert store.list_company_monitors() == []
    archived = store.get_company_monitor("Unknown Labs")
    assert archived["status"] == "removed"
    assert store.monitor_job_ids(archived["id"]) == [job.id]
    store.close()


def test_seed_is_idempotent_and_force_does_not_resave_new_jobs():
    cfg, store = _setup()
    first = seed_monitors(cfg, store)
    later = Job(source="indeed", title="Later", company="Later Co", url="https://x/later").ensure_id()
    store.upsert_job(later)
    store.update_score(later.id, 80, "Strong", "fit")

    second = seed_monitors(cfg, store)
    forced = seed_monitors(cfg, store, force=True)

    assert first["total"] == 2
    assert second["already_seeded"] is True and second["seeded"] is False
    assert forced["seeded"] is True and forced["legacy_saved"] == 0
    assert store.get_job_review(later.id) is None
    assert len(store.list_company_monitors()) == 2
    store.close()


def test_seed_keeps_configured_monitor_explicit_when_application_exists():
    cfg, store = _setup()
    job = Job(source="ats", title="Engineer", company="Databricks", url="https://x/dbx").ensure_id()
    store.upsert_job(job)
    store.set_application(Application(
        job_id=job.id, status="interview", company="Databricks", applied_at="2026-07-15",
    ))

    seed_monitors(cfg, store)

    monitor = store.get_company_monitor("databricks")
    assert monitor["origins"] == ["config"]
    assert len(store.list_company_monitors()) == 2
    store.close()


def _applied(store, *companies):
    for company in companies:
        job = Job(source="inbox", title="Analyst", company=company,
                  url=f"https://x/{company}").ensure_id()
        store.upsert_job(job)
        store.set_application(Application(
            job_id=job.id, status="applied", company=company, applied_at="2026-07-15",
        ))


def test_suggest_probes_only_unwatched_companies(monkeypatch):
    cfg, store = _setup()  # search.companies already holds databricks + Acme
    _applied(store, "Databricks", "Junk Notifications", "Tide")
    probed = []

    def fake_resolve(company, provider=None, slug=None):
        probed.append(company)
        return ("Tide", "greenhouse", "tide") if company == "Tide" else None

    monkeypatch.setattr("jobscope.ingest.ats.resolve_board", fake_resolve)

    suggestions = suggest_boards(cfg, store)

    # Already configured, so never worth a network probe.
    assert "Databricks" not in probed
    assert probed == ["Junk Notifications", "Tide"]
    # Only the company with a real board is suggested; junk parses resolve to nothing.
    assert suggestions == [{
        "applied_as": "Tide", "company": "Tide", "provider": "greenhouse", "slug": "tide",
        "entry": "Tide|greenhouse|tide", "url": board_url("greenhouse", "tide"),
    }]
    store.close()


def test_suggest_caps_the_number_of_probes(monkeypatch):
    cfg, store = _setup()
    _applied(store, "Alpha Co", "Bravo Co", "Charlie Co")
    probed = []
    monkeypatch.setattr("jobscope.ingest.ats.resolve_board",
                        lambda company, **_kwargs: probed.append(company))

    suggest_boards(cfg, store, limit=2)

    assert len(probed) == 2
    store.close()


def test_suggest_survives_a_failing_probe(monkeypatch):
    cfg, store = _setup()
    _applied(store, "Broken Co", "Tide")

    def flaky(company, provider=None, slug=None):
        if company == "Broken Co":
            raise RuntimeError("board probe exploded")
        return ("Tide", "greenhouse", "tide")

    monkeypatch.setattr("jobscope.ingest.ats.resolve_board", flaky)

    suggestions = suggest_boards(cfg, store)

    assert [item["company"] for item in suggestions] == ["Tide"]
    store.close()