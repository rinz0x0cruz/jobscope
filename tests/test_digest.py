"""Tests for the new-match digest (`jobscope new --email` / track.send_digest).

Deterministic and offline: email.send is monkeypatched, so no SMTP is touched.
Freshness is controlled via the `digest:last` marker (upsert stamps first_seen=now).
"""
import os
import tempfile
import json

import pytest

from jobscope.apply import track
from jobscope.cli import main
from jobscope.apply.track import _digest_body
from jobscope.core.model import Job
from jobscope.core.store import Store


def _job(title, company, tier, score, *, url="", remote=True, loc=""):
    return Job(source="indeed", title=title, company=company, url=url or f"u-{title}",
               tier=tier, score=score, is_remote=remote, location=loc).ensure_id()


def _store(tmp):
    return Store(os.path.join(tmp, "d.db"))


def test_first_run_baselines_marker_without_sending(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 80))
        n = track.send_digest({"email": {"enabled": True}}, store)
        assert n == 0                          # first run never floods the inbox
        assert not sent
        assert store.meta_get("digest:last")   # marker baselined for next time
        store.close()


def test_sends_new_strong_good_since_marker(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda cfg, subject, text, html=None, **kwargs:
        sent.append((subject, text, html, kwargs)) or True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")  # anything upserted after is fresh
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        store.upsert_job(_job("Detection Engineer", "Globex", "Good", 60))
        store.upsert_job(_job("Sales Rep", "ShopCo", "Skip", 20))   # wrong tier -> excluded
        n = track.send_digest({"email": {"enabled": True}}, store)
        assert n == 2
        assert len(sent) == 1
        subject, text, html, kwargs = sent[0]
        assert subject == "jobscope: 2 jobs to review"
        assert "Acme" in text and "Globex" in text and "ShopCo" not in text
        assert kwargs["message_id"].startswith("jobscope-digest-")
        assert kwargs["raise_errors"] is True
        assert store.meta_get("digest:last") > "2000-01-01T00:00:00Z"   # marker advanced
        assert store.meta_get(track._DIGEST_INTENT_KEY) is None
        store.close()


def test_singular_subject(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send",
                        lambda cfg, subject, *a, **k: sent.append(subject) or True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        track.send_digest({"email": {"enabled": True}}, store)
        assert sent == ["jobscope: 1 job to review"]
        store.close()


def test_no_new_matches_no_send(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 80))
        store.meta_set("digest:last", "2999-01-01T00:00:00Z")   # future marker -> nothing fresh
        n = track.send_digest({"email": {"enabled": True}}, store)
        assert n == 0 and not sent
        store.close()


def test_email_disabled_is_noop(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 80))
        n = track.send_digest({"email": {"enabled": False}}, store)
        assert n == 0 and not sent
        assert store.meta_get("digest:last") == "2000-01-01T00:00:00Z"   # marker untouched
        store.close()


def test_failed_send_leaves_marker_for_retry(monkeypatch):
    sent_ids = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda *args, **kwargs: sent_ids.append(kwargs["message_id"]) or False,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        n = track.send_digest({"email": {"enabled": True}}, store)
        assert n == 1                                                    # attempted
        assert store.meta_get("digest:last") == "2000-01-01T00:00:00Z"   # NOT advanced -> retried
        blocked = track.send_digest_result({"email": {"enabled": True}}, store)
        assert blocked.attempted == 1 and blocked.sent is False
        assert "explicit" in blocked.detail
        assert len(sent_ids) == 1
        result = track.send_digest_result(
            {"email": {"enabled": True}}, store, retry_intent=True,
        )
        assert result.attempted == 1 and result.sent is False
        assert sent_ids[0] == sent_ids[1]
        intent = json.loads(store.meta_get(track._DIGEST_INTENT_KEY))
        assert intent["state"] == "retryable"
        store.close()


def test_unknown_digest_outcome_blocks_second_smtp_call(monkeypatch):
    from jobscope.deliver import email

    sent_ids = []

    def fail_unknown(*_args, **kwargs):
        sent_ids.append(kwargs["message_id"])
        raise email.EmailDeliveryError(
            "SMTPServerDisconnected", outcome="delivery_unknown",
        )

    monkeypatch.setattr("jobscope.deliver.email.send", fail_unknown)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))

        first = track.send_digest_result({"email": {"enabled": True}}, store)
        second = track.send_digest_result({"email": {"enabled": True}}, store)

        assert first.sent is False and "unknown" in first.detail
        assert second.sent is False and "unresolved" in second.detail
        assert len(sent_ids) == 1
        intent = json.loads(store.meta_get(track._DIGEST_INTENT_KEY))
        assert intent["state"] == "delivery_unknown"
        assert intent["message_id"] == sent_ids[0]
        assert store.meta_get("digest:last") == "2000-01-01T00:00:00Z"
        store.close()


def test_cli_digest_reports_unknown_outcome_as_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        track, "send_digest_result",
        lambda *_args, **_kwargs: track.DigestResult(
            1, False, "delivery outcome unresolved",
        ),
    )

    assert main(["--db", str(tmp_path / "digest.db"), "new", "--email"]) == 1
    assert "digest not sent: delivery outcome unresolved" in capsys.readouterr().err


def test_stale_digest_claim_becomes_unknown_before_any_retry(monkeypatch):
    message_id = "jobscope-digest-crash@example.com"
    intent = {
        "version": 1,
        "state": "sending",
        "marker": "2000-01-01T00:00:00Z",
        "next_marker": "2026-07-01T00:00:00Z",
        "job_ids": ["job:one"],
        "message_id": message_id,
        "subject": "Subject",
        "text": "Body",
        "html": "",
        "created_at": "2026-07-01T00:00:00Z",
        "attempted_at": "2026-07-01T00:00:00Z",
        "last_outcome": "",
    }
    smtp_calls = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda *_args, **_kwargs: smtp_calls.append(True) or True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", intent["marker"])
        store.meta_set(track._DIGEST_INTENT_KEY, track._encode_digest_intent(intent))

        result = track.send_digest_result({"email": {"enabled": True}}, store)

        assert result.sent is False and "unresolved" in result.detail
        assert smtp_calls == []
        stored = json.loads(store.meta_get(track._DIGEST_INTENT_KEY))
        assert stored["state"] == "delivery_unknown"
        assert stored["message_id"] == message_id
        assert store.meta_get("digest:last") == intent["marker"]
        store.close()


def test_accepted_submission_without_finalization_never_reports_success(monkeypatch):
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *_args, **_kwargs: True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        monkeypatch.setattr(store, "meta_finalize_intent", lambda *_a, **_k: False)

        result = track.send_digest_result({"email": {"enabled": True}}, store)

        assert result.sent is False and "conflicted" in result.detail
        assert store.meta_get("digest:last") == "2000-01-01T00:00:00Z"
        store.close()


def test_corrupt_digest_intent_blocks_sending_and_reconciliation(monkeypatch):
    smtp_calls = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda *_args, **_kwargs: smtp_calls.append(True) or True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        store.meta_set(track._DIGEST_INTENT_KEY, '{"state": "ready"')

        result = track.send_digest_result({"email": {"enabled": True}}, store)
        reconciled = track.reconcile_digest_delivery({"email": {"enabled": True}}, store)

        assert result.sent is False and "invalid" in result.detail
        assert reconciled == {"ok": False, "code": "invalid_digest_intent"}
        assert smtp_calls == []
        assert store.meta_get("digest:last") == "2000-01-01T00:00:00Z"
        store.close()


def test_digest_message_id_is_stable_across_job_discovery_order(monkeypatch):
    ids = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda *_args, **kwargs: ids.append(kwargs["message_id"]) or True,
    )
    marker = "2000-01-01T00:00:00Z"
    for order in (["Acme", "Globex"], ["Globex", "Acme"]):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.meta_set("digest:last", marker)
            for company in order:
                store.upsert_job(_job(f"Security Engineer {company}", company, "Strong", 80))
            track.send_digest_result(
                {"email": {"enabled": True, "from_addr": "me@example.com"}}, store,
            )
            store.close()

    assert len(ids) == 2 and ids[0] == ids[1]
    assert ids[0].endswith("@example.com")


def test_digest_reports_matches_beyond_the_batch_cap(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda cfg, subject, text, html=None, **kwargs: sent.append((text, html)) or True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        for index in range(track._DIGEST_MAX_ROWS + 3):
            store.upsert_job(_job(f"Security Engineer {index}", f"Co{index}", "Strong", 80))

        result = track.send_digest_result({"email": {"enabled": True}}, store)

        assert result.attempted == track._DIGEST_MAX_ROWS
        text, html = sent[0]
        assert "3 more new match(es) remain in your review queue." in text
        assert "3 more new match(es) remain in your review queue." in html
        store.close()


@pytest.mark.parametrize(
    ("status", "count", "expected_ok", "expected_state"),
    [
        ("not_found", 0, True, "retryable"),
        ("sent", 1, True, None),
        ("multiple", 2, False, "delivery_unknown"),
    ],
)
def test_reconcile_unknown_digest_by_exact_sent_evidence(
    monkeypatch, status, count, expected_ok, expected_state,
):
    from jobscope.deliver import email

    sent_ids = []

    def fail_unknown(*_args, **kwargs):
        sent_ids.append(kwargs["message_id"])
        raise email.EmailDeliveryError(
            "SMTPServerDisconnected", outcome="delivery_unknown",
        )

    monkeypatch.setattr("jobscope.deliver.email.send", fail_unknown)
    monkeypatch.setattr(
        "jobscope.ingest.inbox.find_sent_message",
        lambda _cfg, message_id: {
            "ok": True, "code": status, "status": status,
            "count": count, "message_id": message_id,
        },
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        marker = "2000-01-01T00:00:00Z"
        store.meta_set("digest:last", marker)
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        track.send_digest_result({"email": {"enabled": True}}, store)

        result = track.reconcile_digest_delivery(
            {"email": {"enabled": True}}, store,
        )

        assert result["ok"] is expected_ok
        assert result["status"] == status
        assert result["count"] == count
        assert result["message_id"] == sent_ids[0]
        raw = store.meta_get(track._DIGEST_INTENT_KEY)
        if expected_state is None:
            assert raw is None
            assert store.meta_get("digest:last") > marker
        else:
            assert json.loads(raw)["state"] == expected_state
            assert store.meta_get("digest:last") == marker
        store.close()


def test_digest_body_escapes_and_lists():
    jobs = [
        _job("Sec & <Eng>", "A<b>Co", "Strong", 90, url="https://x/y?a=1&b=2", remote=False, loc="NYC"),
        _job("Detection Eng", "Globex", "Good", 55, remote=True),
    ]
    text, html = _digest_body(jobs)
    assert "Sec & <Eng>" in text and "Detection Eng" in text        # plain text unescaped
    assert "&lt;Eng&gt;" in html and "A&lt;b&gt;Co" in html         # HTML escapes angle brackets
    assert "a=1&amp;b=2" in html                                    # href escaped
    assert "<a href=" in html                                       # role is linked
    assert "Remote" in html                                         # remote job -> "Remote" location


def test_digest_prioritizes_pending_monitored_then_discovery(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "jobscope.deliver.email.send",
        lambda cfg, subject, text, html=None, **kwargs: sent.append((subject, text, html)) or True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        monitored = _job("Monitored Role", "Acme", "Good", 60)
        discovery = _job("Discovery Role", "Globex", "Strong", 90)
        dismissed = _job("Dismissed Role", "Nope", "Strong", 99)
        for job in (monitored, discovery, dismissed):
            store.upsert_job(job)
        store.set_job_review(monitored.id, "pending", origins=["monitored"])
        store.set_job_review(discovery.id, "pending", origins=["discovery"])
        store.set_job_review(dismissed.id, "dismissed", origins=["monitored"])

        result = track.send_digest_result({"email": {"enabled": True}}, store)

        assert result.attempted == 2
        _subject, text, html = sent[0]
        assert text.index("Monitored companies") < text.index("Discovery")
        assert "Monitored Role" in text and "Discovery Role" in text
        assert "Dismissed Role" not in text
        assert "<h3>Monitored companies" in html
        store.close()
