import os
import tempfile

import pytest

from jobscope.core.store import Store


def _store():
    tmp = tempfile.mkdtemp()
    return Store(os.path.join(tmp, "campaigns.db"))


def test_campaign_draft_edit_invalidates_individual_approval():
    store = _store()
    campaign = store.create_outreach_campaign("India security", 3)
    target = store.upsert_outreach_campaign_target(
        campaign["id"], "Acme Security", "acme security",
        rank_score=84.5, region_score=1, compensation_score=0.8,
        growth_score=0.7, evidence_coverage=0.9,
        evidence={"region": ["Bengaluru security role"]},
    )

    draft = store.set_outreach_campaign_draft(
        target["id"], selected_email="Recruiter@acme.example",
        selected_source="hunter", selected_confidence="medium",
        subject="Security engineering", body="Hello from Jobscope.",
        resume_path="resume.pdf",
    )
    assert draft["state"] == "draft"
    assert draft["selected_email"] == "recruiter@acme.example"

    approved = store.approve_outreach_campaign_target(target["id"])
    assert approved["state"] == "approved" and approved["approval_hash"]
    assert store.outreach_campaign_approval_valid(target["id"]) is True

    edited = store.set_outreach_campaign_draft(
        target["id"], selected_email=approved["selected_email"],
        subject=approved["subject"], body="A revised message.",
        resume_path=approved["resume_path"],
    )
    assert edited["state"] == "draft"
    assert edited["approval_hash"] == "" and edited["approved_at"] == ""
    assert store.outreach_campaign_approval_valid(target["id"]) is False
    store.approve_outreach_campaign_target(target["id"])
    assert store.claim_outreach_campaign_target_send(target["id"]) is True
    assert store.claim_outreach_campaign_target_send(target["id"]) is False
    with pytest.raises(ValueError, match="send is in progress"):
        store.set_outreach_campaign_draft(
            target["id"], selected_email=edited["selected_email"],
            subject=edited["subject"], body="Concurrent edit",
        )
    store.close()


def test_delivery_unknown_requires_explicit_resolution():
    store = _store()
    campaign = store.create_outreach_campaign("Unknown delivery", 1)
    target = store.upsert_outreach_campaign_target(
        campaign["id"], "Acme", "acme", rank_score=80,
    )
    store.set_outreach_campaign_draft(
        target["id"], selected_email="recruiter@acme.example",
        subject="Hello", body="Body",
    )
    store.approve_outreach_campaign_target(target["id"])
    assert store.claim_outreach_campaign_target_send(target["id"], "message@example.com")
    store.mark_outreach_campaign_delivery_unknown(target["id"], "SMTPServerDisconnected")

    draft = store.resolve_outreach_campaign_delivery(target["id"], "not_sent")
    assert draft["state"] == "draft" and draft["approval_hash"] == ""
    assert draft["error_code"] == "" and draft["outbound_message_id"] == "message@example.com"
    store.close()


def test_draft_campaign_delete_removes_unsent_targets_and_runs():
    store = _store()
    campaign = store.create_outreach_campaign("Disposable draft", 1)
    target = store.upsert_outreach_campaign_target(
        campaign["id"], "Acme", "acme", rank_score=80,
    )
    store.conn.execute(
        "INSERT INTO outreach_campaign_runs (id, campaign_id, status, started_at) "
        "VALUES (?, ?, 'completed', ?)",
        ("run:empty", campaign["id"], campaign["created_at"]),
    )
    store.conn.commit()

    deleted = store.delete_draft_outreach_campaign(campaign["id"])

    assert deleted["id"] == campaign["id"]
    assert store.get_outreach_campaign(campaign["id"]) is None
    assert store.get_outreach_campaign_target(target["id"]) is None
    assert store.conn.execute(
        "SELECT COUNT(*) FROM outreach_campaign_runs WHERE campaign_id = ?",
        (campaign["id"],),
    ).fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize("unsafe", ["active", "sent", "delivery_unknown"])
def test_draft_campaign_delete_refuses_status_or_delivery_history(unsafe):
    store = _store()
    campaign = store.create_outreach_campaign("Retained history", 1)
    target = store.upsert_outreach_campaign_target(
        campaign["id"], "Acme", "acme", rank_score=80,
    )
    if unsafe == "active":
        store.set_outreach_campaign_status(campaign["id"], "active")
    elif unsafe == "sent":
        store.conn.execute(
            "UPDATE outreach_campaign_targets SET state = 'sent', sent_at = ? WHERE id = ?",
            (campaign["created_at"], target["id"]),
        )
        store.conn.commit()
    else:
        store.conn.execute(
            "UPDATE outreach_campaign_targets SET error_code = 'delivery_unknown' WHERE id = ?",
            (target["id"],),
        )
        store.conn.commit()

    with pytest.raises(ValueError, match=(
        "only draft" if unsafe == "active" else "delivery history"
    )):
        store.delete_draft_outreach_campaign(campaign["id"])

    assert store.get_outreach_campaign(campaign["id"]) is not None
    assert store.get_outreach_campaign_target(target["id"]) is not None
    store.close()