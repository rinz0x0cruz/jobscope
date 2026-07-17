from jobscope.apply import campaigns
from jobscope.core.model import MailEvent


def _sent_target(store, *, company="Acme", domain="acme.example",
                 sent_at="2026-07-17T05:30:00Z", message_id=""):
    campaign = store.create_outreach_campaign("Replies", 1)
    target = store.upsert_outreach_campaign_target(
        campaign["id"], company, company.lower(), rank_score=80,
    )
    contacts = [{"email": f"recruiter@{domain}", "source": "hunter",
                 "confidence": "medium", "note": "recruiter"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain=domain, contacts=contacts, state="draft",
    )
    store.set_outreach_campaign_draft(
        target["id"], domain=domain, contacts=contacts,
        selected_email=f"recruiter@{domain}", subject="Hello", body="Body",
        resume_path="resume.pdf",
    )
    store.approve_outreach_campaign_target(target["id"])
    assert store.claim_outreach_campaign_target_send(target["id"], message_id)
    store.mark_outreach_campaign_target_sent(target["id"], sent_at)
    return target["id"]


def test_reconcile_replies_links_only_post_send_same_domain_mail(tmp_path):
    from jobscope.core.store import Store

    store = Store(str(tmp_path / "reply.db"))
    target_id = _sent_target(store)
    store.upsert_mail_event(MailEvent(
        account="me@example.com", message_id="<reply@acme>",
        from_addr="person@acme.example", from_domain="acme.example",
        subject="Re: Hello", date="2026-07-17T06:00:00Z", signal="recruiter",
        snippet="Thanks, let's talk.",
    ).ensure_id())

    result = campaigns.reconcile_replies(store)

    target = store.get_outreach_campaign_target(target_id)
    assert result == {"replied": 1, "opted_out": 0}
    assert target["state"] == "replied" and target["replied_at"] == "2026-07-17T06:00:00Z"
    assert target["reply_event_id"]
    history = store.outreach_campaign_history()
    assert history[0]["reply_from"] == "person@acme.example"
    assert history[0]["reply_subject"] == "Re: Hello"
    assert "Thanks" not in str(target)
    store.close()


def test_reconcile_optout_suppresses_email_and_domain(tmp_path):
    from jobscope.core.store import Store

    store = Store(str(tmp_path / "optout.db"))
    target_id = _sent_target(store)
    store.upsert_mail_event(MailEvent(
        account="me@example.com", message_id="<stop@acme>",
        from_addr="person@acme.example", from_domain="acme.example",
        subject="Please remove me", date="2026-07-17T06:00:00Z", signal="other",
        snippet="Do not contact this address again.",
    ).ensure_id())

    result = campaigns.reconcile_replies(store)

    assert result == {"replied": 0, "opted_out": 1}
    assert store.get_outreach_campaign_target(target_id)["state"] == "opted_out"
    assert store.is_outreach_suppressed("email", "person@acme.example")
    assert store.is_outreach_suppressed("domain", "acme.example")
    assert all("snippet" not in suppression for suppression in store.outreach_suppressions())
    store.close()


def test_reconcile_prefers_exact_outbound_message_thread(tmp_path):
    from jobscope.core.store import Store

    store = Store(str(tmp_path / "thread.db"))
    outbound_id = "jobscope-campaign-exact@example.com"
    target_id = _sent_target(store, message_id=outbound_id)
    unrelated = MailEvent(
        account="me@example.com", message_id="<other@acme>",
        thread_id="subj:hello", from_addr="other@acme.example",
        from_domain="acme.example", subject="A separate note",
        date="2026-07-17T05:45:00Z", signal="campaign_reply",
    ).ensure_id()
    exact = MailEvent(
        account="me@example.com", message_id="<exact@acme>",
        thread_id=outbound_id, from_addr="recruiter@acme.example",
        from_domain="acme.example", subject="Re: Hello",
        date="2026-07-17T06:00:00Z", signal="campaign_reply",
    ).ensure_id()
    store.upsert_mail_event(unrelated)
    store.upsert_mail_event(exact)

    assert campaigns.reconcile_replies(store) == {"replied": 1, "opted_out": 0}
    target = store.get_outreach_campaign_target(target_id)
    assert target["reply_event_id"] == exact.id
    store.close()


def test_domain_fallback_refuses_ambiguous_outstanding_targets(tmp_path):
    from jobscope.core.store import Store

    store = Store(str(tmp_path / "ambiguous.db"))
    first_id = _sent_target(
        store, company="Acme One", domain="acme.example",
        sent_at="2026-07-01T05:30:00Z", message_id="first@example.com",
    )
    second_id = _sent_target(
        store, company="Acme Two", domain="acme.example",
        sent_at="2026-07-17T05:30:00Z", message_id="second@example.com",
    )
    event = MailEvent(
        account="me@example.com", message_id="<generic@acme>",
        thread_id="subj:hello", from_addr="person@acme.example",
        from_domain="acme.example", subject="A new thread",
        date="2026-07-17T06:00:00Z", signal="campaign_reply",
    ).ensure_id()
    store.upsert_mail_event(event)

    assert campaigns.reconcile_replies(store) == {"replied": 0, "opted_out": 0}
    assert store.get_outreach_campaign_target(first_id)["state"] == "sent"
    assert store.get_outreach_campaign_target(second_id)["state"] == "sent"
    store.close()


def test_sync_replies_fetches_inbox_then_reconciles(tmp_path, monkeypatch):
    from jobscope.core.store import Store

    store = Store(str(tmp_path / "sync.db"))
    target_id = _sent_target(store, message_id="jobscope-campaign-sync@example.com")
    cfg = {"inbox": {"enabled": True, "accounts": [{"email": "me@example.com"}]}}

    def fake_inbox_run(_cfg, current_store, **_kwargs):
        current_store.upsert_mail_event(MailEvent(
            account="me@example.com", message_id="<sync@acme>",
            thread_id="jobscope-campaign-sync@example.com",
            from_addr="recruiter@acme.example", from_domain="acme.example",
            subject="Re: Hello", date="2026-07-17T06:00:00Z",
            signal="campaign_reply",
        ).ensure_id())
        return 0

    monkeypatch.setattr("jobscope.ingest.inbox.run", fake_inbox_run)

    result = campaigns.sync_replies(cfg, store)

    assert result["ok"] and result["inbox_status"] == "ok" and result["replied"] == 1
    assert store.get_outreach_campaign_target(target_id)["state"] == "replied"
    assert store.meta_get("campaign:replies:last_checked_at") == result["checked_at"]
    store.close()


def test_tick_checks_replies_before_one_delivery(monkeypatch):
    order = []
    monkeypatch.setattr(
        campaigns, "sync_replies",
        lambda *_args, **_kwargs: order.append("replies") or {
            "ok": True, "inbox_status": "ok", "replied": 0, "opted_out": 0,
        },
    )
    monkeypatch.setattr(
        campaigns, "send_next_approved",
        lambda *_args, **_kwargs: order.append("send") or {
            "ok": True, "sent": True, "code": "",
        },
    )

    result = campaigns.tick({}, object())

    assert order == ["replies", "send"]
    assert result["sent"] is True