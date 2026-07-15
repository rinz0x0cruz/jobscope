"""Tests for the new-match digest (`jobscope new --email` / track.send_digest).

Deterministic and offline: email.send is monkeypatched, so no SMTP is touched.
Freshness is controlled via the `digest:last` marker (upsert stamps first_seen=now).
"""
import os
import tempfile

from jobscope.apply import track
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
        lambda cfg, subject, text, html=None, **k: sent.append((subject, text, html)) or True)
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")  # anything upserted after is fresh
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        store.upsert_job(_job("Detection Engineer", "Globex", "Good", 60))
        store.upsert_job(_job("Sales Rep", "ShopCo", "Skip", 20))   # wrong tier -> excluded
        n = track.send_digest({"email": {"enabled": True}}, store)
        assert n == 2
        assert len(sent) == 1
        subject, text, html = sent[0]
        assert subject == "jobscope: 2 new matches"
        assert "Acme" in text and "Globex" in text and "ShopCo" not in text
        assert store.meta_get("digest:last") > "2000-01-01T00:00:00Z"   # marker advanced
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
        assert sent == ["jobscope: 1 new match"]
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
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: False)  # transient failure
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.meta_set("digest:last", "2000-01-01T00:00:00Z")
        store.upsert_job(_job("Security Engineer", "Acme", "Strong", 88))
        n = track.send_digest({"email": {"enabled": True}}, store)
        assert n == 1                                                    # attempted
        assert store.meta_get("digest:last") == "2000-01-01T00:00:00Z"   # NOT advanced -> retried
        result = track.send_digest_result({"email": {"enabled": True}}, store)
        assert result.attempted == 1 and result.sent is False
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
