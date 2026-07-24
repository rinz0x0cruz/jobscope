from datetime import datetime, timezone
import os

import pytest

from jobscope.apply import campaigns
from jobscope.core.config import load_config
from jobscope.core.model import Application, Job, MailEvent, Resume
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


def test_manual_send_does_not_activate_the_campaign(seeded, monkeypatch):
    cfg, store = seeded
    created = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )
    target = created["targets"][0]
    contacts = [{"email": "recruiter@acme.example", "source": "hunter",
                 "confidence": "medium", "note": "security recruiter"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain="acme.example", contacts=contacts, state="draft",
    )
    campaigns.update_draft(
        cfg, store, target["id"], selected_email="recruiter@acme.example",
    )
    campaigns.approve_target(cfg, store, target["id"], now=NOW)
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send", lambda *args, **kwargs: sent.append(kwargs) or True,
    )

    result = campaigns.send_target(
        cfg, store, target["id"], now=NOW,
        ignore_schedule=True, allow_inactive=True,
    )

    assert result["ok"] and result["sent"]
    assert sent[0]["to"] == "recruiter@acme.example"
    assert store.get_outreach_campaign(target["campaign_id"])["status"] == "draft"


def test_engagement_activity_groups_threads_without_outbound_secrets(seeded):
    cfg, store = seeded
    resume_path = store.get_resume().source_path

    def sent_target(campaign_id, company, key, *, sent_at, application_job_id="",
                    source_target_id="", followup_number=0, recipient="recruiter@acme.example"):
        target = store.upsert_outreach_campaign_target(
            campaign_id, company, key,
            application_job_id=application_job_id,
            source_target_id=source_target_id,
            followup_number=followup_number,
            recipient_locked=bool(application_job_id or source_target_id),
        )
        store.set_outreach_campaign_draft(
            target["id"], selected_email=recipient,
            subject=f"Private subject {followup_number}",
            body="PRIVATE-OUTBOUND-BODY-CANARY",
            resume_path=resume_path,
        )
        store.approve_outreach_campaign_target(target["id"])
        assert store.claim_outreach_campaign_target_send(
            target["id"], f"PRIVATE-MESSAGE-ID-{followup_number}@example.test",
        )
        store.mark_outreach_campaign_target_sent(target["id"], sent_at)
        return store.get_outreach_campaign_target(target["id"])

    cold_campaign = store.create_outreach_campaign("Cold", 1, purpose="cold")
    cold = sent_target(
        cold_campaign["id"], "Acme Security", "acme security",
        sent_at="2026-07-10T05:30:00Z",
    )
    cold_followups = store.create_outreach_campaign("Cold follow-ups", 1, purpose="followup")
    cold_followup = sent_target(
        cold_followups["id"], "Acme Security", "acme security",
        sent_at="2026-07-17T05:30:00Z", source_target_id=cold["id"],
        followup_number=1,
    )
    nested_followups = store.create_outreach_campaign(
        "Second cold follow-ups", 1, purpose="followup",
    )
    nested_followup = sent_target(
        nested_followups["id"], "Acme Security", "acme security",
        sent_at="2026-07-18T05:30:00Z", source_target_id=cold_followup["id"],
        followup_number=2,
    )
    reply = MailEvent(
        account="me@example.com", message_id="<PRIVATE-REPLY-ID@example.test>",
        from_addr="recruiter@acme.example", from_domain="acme.example",
        subject="Re: Private subject 2", date="2026-07-18T05:30:00Z",
        signal="campaign_reply", snippet="Thanks, let us schedule a call.",
    ).ensure_id()
    store.upsert_mail_event(reply)
    store.mark_outreach_campaign_target_reply(
        nested_followup["id"], reply.date, event_id=reply.id,
    )

    job = store.jobs()[0]
    store.set_application(Application(
        job_id=job.id, status="applied", company=job.company,
        applied_at="2026-07-11T05:30:00Z",
    ))
    store.mark_outreach(job.id, "application@acme.example", "2026-07-12T05:30:00Z")
    application_followups = store.create_outreach_campaign(
        "Application follow-ups", 1, purpose="followup",
    )
    sent_target(
        application_followups["id"], job.company, "acme application",
        sent_at="2026-07-18T05:30:00Z", application_job_id=job.id,
        followup_number=1, recipient="application@acme.example",
    )

    activity = campaigns.engagement_activity(store)

    assert len(activity) == 2
    cold_thread = next(item for item in activity if item["kind"] == "cold")
    application_thread = next(item for item in activity if item["kind"] == "application")
    assert cold_thread["followup_count"] == 2
    assert cold_thread["reply_count"] == 1
    assert cold_thread["state"] == "replied"
    assert [event["direction"] for event in cold_thread["events"]] == [
        "outbound", "outbound", "outbound", "inbound",
    ]
    assert cold_thread["events"][-1]["summary"] == "Thanks, let us schedule a call."
    assert application_thread["application_job_id"] == job.id
    assert application_thread["outbound_count"] == 2
    assert application_thread["followup_count"] == 1
    serialized = str(activity)
    assert "PRIVATE-OUTBOUND-BODY-CANARY" not in serialized
    assert "PRIVATE-MESSAGE-ID" not in serialized
    assert "PRIVATE-REPLY-ID" not in serialized
    assert resume_path not in serialized


def test_engagement_activity_dedupes_case_variant_direct_send(seeded):
    _cfg, store = seeded
    job = store.jobs()[0]
    direct_sent_at = "2026-07-18T05:30:00+00:00"
    campaign_sent_at = "2026-07-18T05:30:00Z"
    store.set_application(Application(
        job_id=job.id, status="applied", company=job.company,
        applied_at="2026-07-10T05:30:00Z",
    ))
    store.mark_outreach(job.id, "Recruiter@Acme.Example", direct_sent_at)
    campaign = store.create_outreach_campaign("Application follow-up", 1, purpose="followup")
    target = store.upsert_outreach_campaign_target(
        campaign["id"], job.company, "acme application",
        application_job_id=job.id, followup_number=1,
    )
    store.set_outreach_campaign_draft(
        target["id"], selected_email="recruiter@acme.example",
        subject="Re: application", body="Private body",
    )
    store.approve_outreach_campaign_target(target["id"])
    assert store.claim_outreach_campaign_target_send(target["id"], "message@example.test")
    store.mark_outreach_campaign_target_sent(target["id"], campaign_sent_at)

    thread = campaigns.engagement_activity(store)[0]

    assert thread["outbound_count"] == 1


def test_engagement_activity_handles_source_cycle_and_same_company_roots(seeded):
    _cfg, store = seeded

    def sent(campaign_id, key, when):
        target = store.upsert_outreach_campaign_target(
            campaign_id, "Acme Security", key,
        )
        store.set_outreach_campaign_draft(
            target["id"], selected_email="recruiter@acme.example",
            subject=key, body="private",
        )
        store.approve_outreach_campaign_target(target["id"])
        assert store.claim_outreach_campaign_target_send(target["id"], f"{key}@example.test")
        store.mark_outreach_campaign_target_sent(target["id"], when)
        return target["id"]

    first_campaign = store.create_outreach_campaign("First", 1, purpose="cold")
    second_campaign = store.create_outreach_campaign("Second", 1, purpose="cold")
    third_campaign = store.create_outreach_campaign("Independent", 1, purpose="cold")
    first = sent(first_campaign["id"], "acme-first", "not-a-date")
    second = sent(second_campaign["id"], "acme-second", "2026-07-18T05:30:00Z")
    sent(third_campaign["id"], "acme-independent", "2026-07-19T05:30:00Z")
    store.conn.execute(
        "UPDATE outreach_campaign_targets SET source_target_id = ? WHERE id = ?",
        (second, first),
    )
    store.conn.execute(
        "UPDATE outreach_campaign_targets SET source_target_id = ? WHERE id = ?",
        (first, second),
    )
    store.conn.commit()

    activity = campaigns.engagement_activity(store)

    assert len(activity) == 2
    assert sorted(thread["outbound_count"] for thread in activity) == [1, 2]
    assert activity[0]["latest_activity_at"] == "2026-07-19T05:30:00Z"


def test_engagement_activity_surfaces_delivery_unknown_without_marking_sent(seeded):
    _cfg, store = seeded
    campaign = store.create_outreach_campaign("Unknown", 1, purpose="cold")
    target = store.upsert_outreach_campaign_target(
        campaign["id"], "Acme Security", "acme unknown",
    )
    store.set_outreach_campaign_draft(
        target["id"], selected_email="recruiter@acme.example",
        subject="Security introduction", body="private",
    )
    store.approve_outreach_campaign_target(target["id"])
    assert store.claim_outreach_campaign_target_send(target["id"], "unknown@example.test")
    store.mark_outreach_campaign_delivery_unknown(target["id"], "private provider detail")

    thread = campaigns.engagement_activity(store)[0]

    assert thread["state"] == "delivery_unknown"
    assert thread["sent_at"]
    assert thread["outbound_count"] == 1
    assert "private provider detail" not in str(thread)


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


def test_successful_contact_retry_clears_prior_discovery_error(seeded, monkeypatch):
    cfg, store = seeded
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    store.set_outreach_campaign_target_state(
        target["id"], "failed", error_code="contact_discovery_failed",
        error_detail="temporary provider failure",
    )
    monkeypatch.setattr(
        "jobscope.apply.outreach.refresh_company_contacts",
        lambda *_args, **_kwargs: {
            "status": "updated", "domain": "acme.example",
            "contacts": [{"email": "careers@acme.example", "source": "role_inbox",
                          "confidence": "low", "note": "manual fallback"}],
        },
    )

    result = campaigns.discover_target(cfg, store, target["id"], force=True, fetch=False)

    assert result["state"] == "needs_contact"
    assert result["error_code"] == ""
    assert result["error_detail"] == ""


def test_off_domain_recruiter_does_not_block_valid_on_domain_contact(seeded, monkeypatch):
    cfg, store = seeded
    target = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )["targets"][0]
    monkeypatch.setattr(
        "jobscope.apply.outreach.refresh_company_contacts",
        lambda *_args, **_kwargs: {
            "status": "updated",
            "domain": "acme.example",
            "contacts": [
                {"email": "agent@agency.example", "source": "recruiter",
                 "confidence": "high", "note": "security recruiter at an agency"},
                {"email": "talent@acme.example", "source": "hunter",
                 "confidence": "medium", "note": "technical recruiter via Hunter.io"},
            ],
        },
    )

    result = campaigns.discover_target(cfg, store, target["id"], fetch=False)

    assert result["state"] == "draft"
    assert result["selected_email"] == "talent@acme.example"
    assert {contact["email"] for contact in result["contacts"]} == {
        "agent@agency.example", "talent@acme.example",
    }


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


def test_bounded_discovery_retries_needs_contact_with_forced_refresh(seeded, monkeypatch):
    cfg, store = seeded
    created = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )
    target = created["targets"][0]
    store.set_outreach_campaign_contacts(
        target["id"], domain="acme.example",
        contacts=[{"email": "careers@acme.example", "source": "role_inbox",
                   "confidence": "low", "note": "manual fallback"}],
    )
    calls = []

    def refreshed(*_args, **kwargs):
        calls.append(kwargs)
        return {
            "status": "updated", "domain": "acme.example",
            "contacts": [{"email": "recruiter@acme.example", "source": "hunter",
                          "confidence": "medium", "note": "security recruiter"}],
        }

    monkeypatch.setattr(
        "jobscope.apply.outreach.refresh_company_contacts", refreshed,
    )

    result = campaigns.discover_pending_targets(
        cfg, store, created["campaign"]["id"], limit=5, fetch=False,
    )

    assert result == {
        "ok": True, "processed": 1, "drafted": 1,
        "needs_contact": 0, "failed": 0, "remaining": 0,
    }
    assert calls == [{"url": "https://acme.example", "force": True, "fetch": False}]
    assert store.get_outreach_campaign_target(target["id"])["selected_email"] == (
        "recruiter@acme.example"
    )


def test_bounded_discovery_retries_contact_discovery_failures(seeded, monkeypatch):
    cfg, store = seeded
    created = campaigns.create_campaign(
        cfg, store, "India security", 1, candidates=["Acme Security"], now=NOW,
    )
    target = created["targets"][0]
    store.set_outreach_campaign_target_state(
        target["id"], "failed", error_code="contact_discovery_failed",
        error_detail="temporary provider failure",
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

    assert result["processed"] == 1
    assert result["drafted"] == 1
    recovered = store.get_outreach_campaign_target(target["id"])
    assert recovered["state"] == "draft"
    assert recovered["error_code"] == ""


def test_build_application_followup_queue_is_idempotent_and_uses_cached_contact(seeded):
    cfg, store = seeded
    cfg["apply"]["followup_days"] = 7
    job = next(job for job in store.jobs() if job.company == "Acme Security")
    store.conn.execute(
        "INSERT INTO applications (job_id, status, company, applied_at, updated) "
        "VALUES (?, 'applied', ?, ?, ?)",
        (job.id, job.company, "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    store.conn.commit()
    store.set_company_contacts(
        job.company, "acme.example", [{
            "email": "recruiter@acme.example", "source": "hunter",
            "confidence": "medium", "note": "security recruiter",
        }],
    )

    created = campaigns.create_followup_campaign(
        cfg, store, "Application follow-ups", 10,
        include_cold=False, now=NOW,
    )

    assert created["campaign"]["purpose"] == "followup"
    assert created["counts"] == {"draft": 1}
    target = created["targets"][0]
    assert target["application_job_id"] == job.id
    assert target["selected_email"] == "recruiter@acme.example"
    assert target["recipient_locked"] is False
    assert "Following up" in target["subject"]
    assert "recently applied" in target["body"]
    with pytest.raises(ValueError, match="no follow-up candidates"):
        campaigns.create_followup_campaign(
            cfg, store, "Duplicate", 10, include_cold=False, now=NOW,
        )


def test_application_followup_reuses_and_locks_prior_outreach_recipient(seeded):
    cfg, store = seeded
    cfg["apply"]["followup_days"] = 7
    job = next(job for job in store.jobs() if job.company == "Acme Security")
    store.conn.execute(
        "INSERT INTO applications (job_id, status, company, applied_at, outreach_at, "
        "outreach_to, updated) VALUES (?, 'applied', ?, ?, ?, ?, ?)",
        (
            job.id, job.company, "2026-06-20T00:00:00Z",
            "2026-07-01T00:00:00Z", "agent@agency.example",
            "2026-07-01T00:00:00Z",
        ),
    )
    store.conn.commit()

    created = campaigns.create_followup_campaign(
        cfg, store, "Application follow-ups", 10,
        include_cold=False, now=NOW,
    )

    target = created["targets"][0]
    assert target["selected_email"] == "agent@agency.example"
    assert target["recipient_locked"] is True
    with pytest.raises(ValueError, match="locked to the original"):
        campaigns.update_draft(
            cfg, store, target["id"], selected_email="other@agency.example",
        )


def test_followup_build_with_missing_resume_leaves_no_campaign(seeded):
    cfg, store = seeded
    job = next(job for job in store.jobs() if job.company == "Acme Security")
    store.conn.execute(
        "INSERT INTO applications (job_id, status, company, applied_at, updated) "
        "VALUES (?, 'applied', ?, ?, ?)",
        (job.id, job.company, "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    store.conn.commit()
    os.remove(store.get_resume().source_path)

    with pytest.raises(ValueError, match="not available on disk"):
        campaigns.create_followup_campaign(
            cfg, store, "Application follow-ups", 10,
            include_cold=False, now=NOW,
        )

    assert store.outreach_campaigns() == []


def test_cold_followup_locks_original_recipient_and_threads_reply(seeded):
    cfg, store = seeded
    cfg["apply"]["followup_days"] = 7
    cold = campaigns.create_campaign(
        cfg, store, "Cold", 1, candidates=["Acme Security"], now=NOW,
    )
    source = cold["targets"][0]
    contacts = [{
        "email": "agent@agency.example", "source": "recruiter",
        "confidence": "high", "note": "original recruiter",
    }]
    store.set_outreach_campaign_contacts(
        source["id"], domain="acme.example", contacts=contacts, state="draft",
    )
    store.set_outreach_campaign_draft(
        source["id"], domain="acme.example", contacts=contacts,
        selected_email="agent@agency.example", subject="Security opportunity",
        body="Original note", resume_path=store.get_resume().source_path,
    )
    store.approve_outreach_campaign_target(source["id"])
    assert store.claim_outreach_campaign_target_send(source["id"], "cold@example.com")
    store.mark_outreach_campaign_target_sent(source["id"], "2026-07-01T00:00:00Z")

    created = campaigns.create_followup_campaign(
        cfg, store, "Cold follow-ups", 10,
        include_applications=False, now=NOW,
    )

    target = created["targets"][0]
    assert target["selected_email"] == "agent@agency.example"
    assert target["recipient_locked"] is True
    assert target["parent_message_id"] == "cold@example.com"
    assert target["subject"] == "Re: Security opportunity"
    assert "earlier note" in target["body"]


@pytest.mark.parametrize(
    ("status", "applied_at", "updated"),
    [
        ("applied", "2026-07-14T00:00:00Z", "2026-07-14T00:00:00Z"),
        ("interview", "2026-06-20T00:00:00Z", "2026-07-10T00:00:00Z"),
    ],
)
def test_cold_followup_respects_latest_application_state(
    seeded, status, applied_at, updated,
):
    cfg, store = seeded
    cfg["apply"]["followup_days"] = 7
    cold = campaigns.create_campaign(
        cfg, store, "Cold", 1, candidates=["Acme Security"], now=NOW,
    )
    source = cold["targets"][0]
    contacts = [{
        "email": "agent@agency.example", "source": "recruiter",
        "confidence": "high", "note": "original recruiter",
    }]
    store.set_outreach_campaign_contacts(
        source["id"], domain="acme.example", contacts=contacts, state="draft",
    )
    store.set_outreach_campaign_draft(
        source["id"], domain="acme.example", contacts=contacts,
        selected_email="agent@agency.example", subject="Security opportunity",
        body="Original note", resume_path=store.get_resume().source_path,
    )
    store.approve_outreach_campaign_target(source["id"])
    assert store.claim_outreach_campaign_target_send(source["id"], "cold@example.com")
    store.mark_outreach_campaign_target_sent(source["id"], "2026-07-01T00:00:00Z")
    job = next(job for job in store.jobs() if job.company == "Acme Security")
    store.conn.execute(
        "INSERT INTO applications (job_id, status, company, applied_at, updated) "
        "VALUES (?, ?, ?, ?, ?)",
        (job.id, status, job.company, applied_at, updated),
    )
    store.conn.commit()

    with pytest.raises(ValueError, match="no follow-up candidates"):
        campaigns.create_followup_campaign(
            cfg, store, "Cold follow-ups", 10,
            include_applications=False, now=NOW,
        )


def test_application_followup_approve_send_and_reply_end_to_end(seeded, monkeypatch):
    cfg, store = seeded
    cfg["apply"]["followup_days"] = 7
    job = next(job for job in store.jobs() if job.company == "Acme Security")
    store.conn.execute(
        "INSERT INTO applications (job_id, status, company, applied_at, updated) "
        "VALUES (?, 'applied', ?, ?, ?)",
        (job.id, job.company, "2026-07-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    )
    store.conn.commit()
    store.set_company_contacts(job.company, "acme.example", [{
        "email": "recruiter@acme.example", "source": "hunter",
        "confidence": "medium", "note": "security recruiter",
    }])
    created = campaigns.create_followup_campaign(
        cfg, store, "Application follow-ups", 10,
        include_cold=False, now=NOW,
    )
    target = created["targets"][0]
    approved = campaigns.approve_target(cfg, store, target["id"], now=NOW)
    campaigns.set_campaign_status(store, created["campaign"]["id"], "active")
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send", lambda *args, **kwargs: sent.append(kwargs) or True,
    )

    result = campaigns.send_target(cfg, store, approved["id"], now=NOW)

    assert result["sent"] is True
    assert sent[0]["to"] == "recruiter@acme.example"
    assert sent[0]["message_id"].startswith("jobscope-campaign-")
    assert sent[0]["in_reply_to"] == ""
    outbound_id = sent[0]["message_id"]
    from jobscope.core.model import MailEvent
    store.upsert_mail_event(MailEvent(
        account="jane@example.com", message_id="<reply@acme.example>",
        thread_id=outbound_id, from_addr="recruiter@acme.example",
        from_domain="acme.example", subject="Re: Following up",
        date="2026-07-17T06:00:00Z", signal="campaign_reply",
    ).ensure_id())
    assert campaigns.reconcile_replies(store) == {"replied": 1, "opted_out": 0}
    stored = store.get_outreach_campaign_target(target["id"])
    assert stored["state"] == "replied" and stored["reply_event_id"]


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
    assert campaigns.get_campaign_detail(store, target["campaign_id"])["counts"] == {
        "delivery_unknown": 1,
    }
    assert campaigns.list_campaigns(store)[0]["counts"] == {"delivery_unknown": 1}
    campaigns.set_campaign_status(store, target["campaign_id"], "paused")
    with pytest.raises(ValueError, match="approve at least one target"):
        campaigns.set_campaign_status(store, target["campaign_id"], "active")


def test_send_next_recovers_only_stale_claims_before_selecting_due_work():
    class Store:
        def __init__(self):
            self.cutoff = ""

        def mark_stale_outreach_campaign_sends_unknown(self, cutoff):
            self.cutoff = cutoff
            return 1

        def due_outreach_campaign_targets(self, *_args, **_kwargs):
            return []

    store = Store()

    result = campaigns.send_next_approved({}, store, now=NOW)

    assert result == {"ok": True, "sent": False, "code": "nothing_due"}
    assert store.cutoff == "2026-07-17T05:15:00Z"


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