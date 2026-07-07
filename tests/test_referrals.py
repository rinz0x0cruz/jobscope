"""Tests for referral surfacing (`apply.referrals`). Deterministic, offline."""
import os
import tempfile

from jobscope.apply import referrals
from jobscope.core.config import load_config
from jobscope.core.model import Contact, Job
from jobscope.core.store import Store


def _store(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "r.db")
    return cfg, Store(cfg["output"]["db_path"])


def _leads(company):
    return [
        Contact(id=f"{company}-gh", company=company, name="Dev One", title="Engineer",
                source="github", profile_url="https://github.com/devone",
                outreach=f"Hi Dev, I came across your profile while researching {company}."),
        Contact(id=f"{company}-s1", company=company, name="Find on LinkedIn",
                source="search", search_url=f"https://linkedin.com/search?q={company}"),
    ]


def _job(company, **over):
    j = Job(source="indeed", title="Security Engineer", company=company,
            url=f"https://x/{company}", tier="Strong")
    for k, v in over.items():
        setattr(j, k, v)
    return j.ensure_id()


def test_paths_for_splits_real_search_and_draft():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        store.save_contacts(_leads("Acme"))
        p = referrals.paths_for(store, "Acme")
        assert len(p["real"]) == 1 and p["real"][0]["source"] == "github"
        assert len(p["searches"]) == 1
        assert p["draft"].startswith("Hi Dev")
        store.close()


def test_pipeline_lists_open_first_then_closed():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        store.upsert_job(_job("OpenCo"))            # OpenCo has a live job
        store.save_contacts(_leads("OpenCo"))
        store.save_contacts(_leads("ClosedCo"))     # leads, but no live job
        items = referrals.pipeline_referrals(store)
        assert [p["company"] for p in items] == ["OpenCo", "ClosedCo"]
        assert items[0]["open"] is True and items[1]["open"] is False
        assert items[0]["tier"] == "Strong"
        store.close()


def test_pipeline_excludes_companies_without_leads():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        store.upsert_job(_job("NoLeadsCo"))
        store.save_contacts(_leads("HasLeads"))
        companies = [p["company"] for p in referrals.pipeline_referrals(store)]
        assert "HasLeads" in companies and "NoLeadsCo" not in companies
        store.close()


def test_render_digest_empty_and_populated():
    assert "no referral paths yet" in referrals.render_digest([])
    items = [{"company": "Acme", "real": [{}], "searches": [{}, {}],
              "leads": [{}, {}, {}], "open": True, "tier": "Strong",
              "status": "", "title": "Security Engineer", "job_id": "x"}]
    text = referrals.render_digest(items)
    assert "Acme" in text and "live role" in text and "1 profile" in text


def test_render_one_shows_profiles_and_draft():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        store.save_contacts(_leads("Acme"))
        p = referrals.paths_for(store, "Acme")
        text = referrals.render_one(_job("Acme"), p)
        assert "real profiles" in text and "github.com/devone" in text
        assert "outreach draft" in text and "Hi Dev" in text
        store.close()


def test_run_digest_per_job_and_bad_id():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        assert referrals.run(cfg, store, job_id="nope") == 1     # bad job id
        job = _job("Acme")
        store.upsert_job(job)
        store.save_contacts(_leads("Acme"))
        assert referrals.run(cfg, store) == 0                    # digest
        assert referrals.run(cfg, store, job_id=job.id) == 0     # per-job
        store.close()


def test_discover_leads_fetches_and_persists(monkeypatch):
    from jobscope.enrich import contacts as enrich_contacts
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        job = _job("FreshCo")
        store.upsert_job(job)
        monkeypatch.setattr(enrich_contacts, "find", lambda company, j: _leads(company))
        p = referrals.discover_leads(cfg, store, job)
        assert len(p["leads"]) == 2 and p["draft"]
        assert len(store.contacts_for("FreshCo")) == 2           # persisted
        store.close()
