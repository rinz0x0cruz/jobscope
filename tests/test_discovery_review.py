import datetime as dt
import os
import tempfile

from jobscope.analyze.review import sync_reviews
from jobscope.core.config import load_config
from jobscope.core.model import Application, Job
from jobscope.core.store import Store
from jobscope.ingest.scrape import DISCOVERY_MARKER, discovery_due


def _setup():
    directory = tempfile.mkdtemp()
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(directory, "review.db")
    cfg["discovery"] = {"enabled": True, "interval_hours": 24}
    return cfg, Store(cfg["output"]["db_path"])


def _scored(store, title: str, url: str, tier="Strong"):
    job = Job(source="indeed", title=title, company="Acme", url=url).ensure_id()
    store.upsert_job(job)
    store.update_score(job.id, 80, tier, "fit")
    return job


def test_review_sync_separates_monitored_and_discovery_and_excludes_applied_skip():
    _cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="greenhouse", slug="acme", added_from="user",
    )
    monitored = _scored(store, "Monitored", "https://x/monitored")
    discovery = _scored(store, "Discovery", "https://x/discovery")
    applied = _scored(store, "Applied", "https://x/applied")
    skipped = _scored(store, "Skipped", "https://x/skipped", tier="Skip")
    store.link_monitor_job(company["id"], monitored.id)
    store.set_application(Application(job_id=applied.id, status="applied", company="Acme"))

    result = sync_reviews(store)

    assert result == {"created": 2, "pending_monitored": 1, "pending_discovery": 1}
    assert store.get_job_review(monitored.id)["origins"] == ["monitored"]
    assert store.get_job_review(discovery.id)["origins"] == ["discovery"]
    assert store.get_job_review(applied.id) is None
    assert store.get_job_review(skipped.id) is None
    store.close()


def test_review_sync_never_resets_saved_or_dismissed_and_merges_origin():
    _cfg, store = _setup()
    company = store.upsert_company_monitor(
        "Acme", provider="lever", slug="acme", added_from="user",
    )
    saved = _scored(store, "Saved", "https://x/saved")
    dismissed = _scored(store, "Dismissed", "https://x/dismissed")
    store.set_job_review(saved.id, "saved", origins=["discovery"])
    store.set_job_review(dismissed.id, "dismissed", origins=["discovery"])
    store.link_monitor_job(company["id"], saved.id)

    sync_reviews(store)

    assert store.get_job_review(saved.id)["state"] == "saved"
    assert store.get_job_review(saved.id)["origins"] == ["discovery", "monitored"]
    assert store.get_job_review(dismissed.id)["state"] == "dismissed"
    store.close()


def test_discovery_cadence_and_disable_switch():
    cfg, store = _setup()
    now = dt.datetime(2026, 7, 16, 12, tzinfo=dt.timezone.utc)
    assert discovery_due(cfg, store, now=now)
    store.meta_set(DISCOVERY_MARKER, "2026-07-16T00:00:00Z")
    assert not discovery_due(cfg, store, now=now)
    assert discovery_due(cfg, store, now=now + dt.timedelta(hours=13))
    cfg["discovery"]["enabled"] = False
    assert not discovery_due(cfg, store, now=now + dt.timedelta(days=5))
    store.close()