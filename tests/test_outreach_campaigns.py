from datetime import datetime, timezone

import pytest

from jobscope.apply import campaigns
from jobscope.core.config import load_config
from jobscope.core.model import Job, Resume
from jobscope.core.store import Store


NOW = datetime(2026, 7, 17, 5, 30, tzinfo=timezone.utc)  # 11:00 Asia/Kolkata


@pytest.fixture
def seeded(tmp_path):
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# Jane Doe\n\nSecurity engineer", encoding="utf-8")
    cfg = load_config(None)
    cfg["output"]["db_path"] = str(tmp_path / "campaigns.db")
    cfg["apply"]["outreach"]["enabled"] = True
    cfg["apply"]["outreach"]["discover"] = False
    cfg["email"]["enabled"] = True
    cfg["email"]["from_addr"] = "jane@example.com"
    store = Store(cfg["output"]["db_path"])
    store.save_resume(Resume(
        full_name="Jane Doe", email="jane@example.com", skills=["cloud security", "python"],
        seniority="senior", years_experience=6, source_path=str(resume_path),
    ))
    job = Job(
        source="test", title="Cloud Security Engineer", company="Acme Security",
        location="Bengaluru, India", company_url="https://acme.example",
        date_posted="2026-07-10", url="https://acme.example/jobs/1",
        salary_max=3_000_000, salary_interval="yearly", currency="INR",
        description="Cloud security and Python engineering.",
    ).ensure_id()
    store.upsert_job(job)
    yield cfg, store
    store.close()


def test_create_discover_approve_and_send_one_target(seeded, monkeypatch):
    cfg, store = seeded
    created = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )
    target = created["targets"][0]
    assert target["rank_score"] > 0 and created["campaign"]["status"] == "draft"

    contacts = [
        {"email": "careers@acme.example", "source": "role_inbox", "confidence": "low",
         "note": "fallback"},
        {"email": "security.recruiter@acme.example", "source": "hunter",
         "confidence": "medium", "note": "security recruiter via Hunter.io"},
    ]
    monkeypatch.setattr(
        "jobscope.apply.outreach.refresh_company_contacts",
        lambda *_args, **_kwargs: {"status": "updated", "domain": "acme.example",
                                   "contacts": contacts},
    )
    drafted = campaigns.discover_target(cfg, store, target["id"], fetch=False)
    assert drafted["state"] == "draft"
    assert drafted["selected_email"] == "security.recruiter@acme.example"
    assert drafted["selected_source"] == "hunter"

    approved = campaigns.approve_target(cfg, store, target["id"], now=NOW)
    assert approved["state"] == "approved" and approved["scheduled_at"] == "2026-07-17T05:30:00Z"
    campaigns.set_campaign_status(store, created["campaign"]["id"], "active")

    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send", lambda *args, **kwargs: sent.append(kwargs) or True,
    )
    result = campaigns.send_next_approved(cfg, store, now=NOW)
    assert result["ok"] and result["sent"]
    assert sent[0]["to"] == "security.recruiter@acme.example"
    assert sent[0]["message_id"].startswith("jobscope-campaign-")
    assert store.get_outreach_campaign_target(target["id"])["state"] == "sent"
    history = store.outreach_campaign_history(created["campaign"]["id"])
    assert history[0]["recipient"] == "security.recruiter@acme.example"
    assert history[0]["outbound_message_id"] == sent[0]["message_id"]
    assert campaigns.send_next_approved(cfg, store, now=NOW)["code"] == "nothing_due"


def test_role_inbox_is_not_auto_selected(seeded, monkeypatch):
    cfg, store = seeded
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    monkeypatch.setattr(
        "jobscope.apply.outreach.refresh_company_contacts",
        lambda *_args, **_kwargs: {
            "status": "updated", "domain": "acme.example",
            "contacts": [{"email": "careers@acme.example", "source": "role_inbox",
                          "confidence": "low", "note": "fallback"}],
        },
    )

    result = campaigns.discover_target(cfg, store, target["id"], fetch=False)

    assert result["state"] == "needs_contact" and result["selected_email"] == ""
    assert result["contacts"][0]["source"] == "role_inbox"


def test_bounded_discovery_prepares_ranked_targets_without_approval(seeded, monkeypatch):
    cfg, store = seeded
    created = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )
    monkeypatch.setattr(
        "jobscope.apply.outreach.refresh_company_contacts",
        lambda *_args, **_kwargs: {
            "status": "updated", "domain": "acme.example",
            "contacts": [{"email": "recruiter@acme.example", "source": "hunter",
                          "confidence": "medium", "note": "security recruiter"}],
        },
    )

    result = campaigns.discover_pending_targets(
        cfg, store, created["campaign"]["id"], limit=5, fetch=False,
    )

    assert result == {
        "ok": True, "processed": 1, "drafted": 1,
        "needs_contact": 0, "failed": 0, "remaining": 0,
    }
    target = store.outreach_campaign_targets(created["campaign"]["id"])[0]
    assert target["state"] == "draft" and target["approval_hash"] == ""


def test_send_rechecks_application_history_after_approval(seeded, monkeypatch):
    cfg, store = seeded
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    contacts = [{"email": "recruiter@acme.example", "source": "apollo",
                 "confidence": "medium", "note": "technical recruiter via Apollo"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain="acme.example", contacts=contacts, state="draft",
    )
    campaigns.update_draft(
        cfg, store, target["id"], selected_email="recruiter@acme.example",
    )
    campaigns.approve_target(cfg, store, target["id"], now=NOW)
    campaigns.set_campaign_status(store, target["campaign_id"], "active")

    job = next(job for job in store.jobs() if job.company == "Acme Security")
    store.conn.execute(
        "INSERT INTO applications (job_id, status, company, updated) VALUES (?, ?, ?, ?)",
        (job.id, "applied", job.company, "2026-07-17T05:31:00Z"),
    )
    store.conn.commit()
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send", lambda *args, **kwargs: sent.append(kwargs) or True,
    )

    result = campaigns.send_target(cfg, store, target["id"], now=NOW)

    assert result["code"] == "application_history" and sent == []
    stored = store.get_outreach_campaign_target(target["id"])
    assert stored["state"] == "skipped" and stored["error_code"] == "application_history"


def test_send_rejects_resume_changed_after_approval(seeded, monkeypatch):
    cfg, store = seeded
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    contacts = [{"email": "recruiter@acme.example", "source": "hunter",
                 "confidence": "medium", "note": "security recruiter"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain="acme.example", contacts=contacts, state="draft",
    )
    drafted = campaigns.update_draft(
        cfg, store, target["id"], selected_email="recruiter@acme.example",
    )
    campaigns.approve_target(cfg, store, target["id"], now=NOW)
    campaigns.set_campaign_status(store, target["campaign_id"], "active")
    with open(drafted["resume_path"], "a", encoding="utf-8") as handle:
        handle.write("\nchanged after approval")
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send", lambda *args, **kwargs: sent.append(kwargs) or True,
    )

    result = campaigns.send_target(cfg, store, target["id"], now=NOW)

    assert result["code"] == "resume_changed" and sent == []
    assert store.get_outreach_campaign_target(target["id"])["state"] == "failed"


def test_sendmail_unknown_outcome_is_locked_and_never_auto_retried(seeded, monkeypatch):
    cfg, store = seeded
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    contacts = [{"email": "recruiter@acme.example", "source": "hunter",
                 "confidence": "medium", "note": "security recruiter"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain="acme.example", contacts=contacts, state="draft",
    )
    campaigns.update_draft(
        cfg, store, target["id"], selected_email="recruiter@acme.example",
    )
    campaigns.approve_target(cfg, store, target["id"], now=NOW)
    campaigns.set_campaign_status(store, target["campaign_id"], "active")

    from jobscope.deliver import email
    monkeypatch.setattr(
        email, "send",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            email.EmailDeliveryError("SMTPServerDisconnected", outcome_unknown=True)
        ),
    )

    result = campaigns.send_target(cfg, store, target["id"], now=NOW)
    stored = store.get_outreach_campaign_target(target["id"])

    assert result["code"] == "delivery_unknown"
    assert stored["state"] == "approved"
    assert stored["error_code"] == "delivery_unknown"
    assert stored["outbound_message_id"].startswith("jobscope-campaign-")
    assert store.due_outreach_campaign_targets("9999-12-31T23:59:59Z") == []
    assert campaigns.send_target(cfg, store, target["id"], now=NOW)["code"] == "delivery_unknown"
    assert store.outreach_campaign_history()[0]["sent_at"] == ""


def test_draft_uses_profile_relevant_security_role_instead_of_backend(seeded):
    cfg, store = seeded
    backend = Job(
        source="test", title="Intermediate Backend Engineer", company="Acme Security",
        location="Remote, India", url="https://acme.example/jobs/backend",
        description="Our platform reduces security and compliance risk.",
        score=99, tier="Skip",
    ).ensure_id()
    store.upsert_job(backend)
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    contacts = [{"email": "recruiter@acme.example", "source": "hunter",
                 "confidence": "medium", "note": "security recruiter"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain="acme.example", contacts=contacts, state="draft",
    )

    drafted = campaigns.update_draft(
        cfg, store, target["id"], selected_email="recruiter@acme.example",
    )

    assert "Cloud Security Engineer" in drafted["subject"]
    assert "Backend Engineer" not in drafted["subject"]