"""Applied-company HR-contact pre-compute: store queries, the opt-in finder
(Hunter.io + Apollo), and the batch scan that feeds the dashboard. Offline."""
import contextlib
import os
import shutil
import tempfile

from jobscope.apply import finder, outreach
from jobscope.core.config import load_config
from jobscope.core.model import Application, Job, MailEvent
from jobscope.core.store import Store


@contextlib.contextmanager
def _tmpstore():
    tmp = tempfile.mkdtemp()
    store = Store(os.path.join(tmp, "t.db"))
    try:
        yield store
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)   # Windows may briefly hold the db handle


def _seed_app(store, company, status, *, company_url="", when="2026-07-01T10:00:00Z"):
    jid = "job:" + company.lower()
    store.upsert_job(Job(id=jid, source="ats", title="Security Engineer", company=company,
                         company_url=company_url, status="open"))
    store.set_application(Application(job_id=jid, status=status, company=company,
                                     title="Security Engineer", applied_at=when, updated=when))


# --- store: active applied companies ----------------------------------------
def test_active_application_companies_excludes_terminal_and_dedupes():
    with _tmpstore() as store:
        _seed_app(store, "Acme", "applied", company_url="https://acme.com", when="2026-07-03T10:00:00Z")
        _seed_app(store, "Globex", "interview", when="2026-07-05T10:00:00Z")
        _seed_app(store, "Initech", "rejected")   # excluded (terminal)
        _seed_app(store, "Umbrella", "offer")      # excluded (terminal)
        rows = store.active_application_companies(limit=25)
        names = [r["company"] for r in rows]
        assert names == ["Globex", "Acme"]         # most-recent first, terminal dropped
        assert rows[1]["company_url"] == "https://acme.com"


def test_company_contacts_roundtrip():
    with _tmpstore() as store:
        contacts = [{"email": "hr@acme.com", "confidence": "medium", "source": "discovered", "note": "x"}]
        store.set_company_contacts("Acme", "acme.com", contacts)
        got = store.get_company_contacts("Acme")
        assert got["domain"] == "acme.com" and got["contacts"] == contacts and got["discovered_at"]
        assert [c["company"] for c in store.list_company_contacts()] == ["Acme"]


# --- finder: opt-in, key-gated, on-domain -----------------------------------
def test_finder_off_without_keys(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_HUNTER_API_KEY", raising=False)
    monkeypatch.delenv("JOBSCOPE_APOLLO_API_KEY", raising=False)
    assert finder.find_contacts(load_config(None), "Acme", "acme.com") == []


def test_finder_hunter_parses_and_filters(monkeypatch):
    monkeypatch.setenv("JOBSCOPE_HUNTER_API_KEY", "k")
    monkeypatch.delenv("JOBSCOPE_APOLLO_API_KEY", raising=False)

    def fake_get_json(url, **_k):
        return {"data": {"emails": [
            {"value": "recruiter@acme.com", "confidence": 92},
            {"value": "noreply@acme.com", "confidence": 99},   # automated -> dropped
            {"value": "someone@other.com", "confidence": 90},  # off-domain -> dropped
        ]}}
    monkeypatch.setattr("jobscope.core.httpx.get_json", fake_get_json)
    out = finder.find_contacts(load_config(None), "Acme", "acme.com")
    assert [c["email"] for c in out] == ["recruiter@acme.com"]
    assert out[0]["source"] == "hunter" and out[0]["confidence"] == "high"


def test_finder_apollo_parses(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_HUNTER_API_KEY", raising=False)
    monkeypatch.setenv("JOBSCOPE_APOLLO_API_KEY", "k")
    monkeypatch.setattr("jobscope.core.httpx.get_json", lambda *a, **k: None)
    monkeypatch.setattr("jobscope.apply.finder._post_json",
                        lambda *a, **k: {"people": [{"email": "talent@acme.com", "title": "Recruiter"}]})
    out = finder.find_contacts(load_config(None), "Acme", "acme.com")
    assert out == [{"email": "talent@acme.com", "confidence": "medium",
                    "source": "apollo", "note": "Recruiter via Apollo"}]


# --- batch discovery --------------------------------------------------------
def _fake_site(url, **_k):
    return '<a href="mailto:careers@acme.com">Careers</a>' if "acme.com" in url else None


def test_discover_company_contacts_ranks_sources(monkeypatch):
    monkeypatch.setattr("jobscope.core.httpx.get_text", _fake_site)
    with _tmpstore() as store:
        # a real recruiter emailed you from the employer domain
        store.upsert_mail_event(MailEvent(
            account="me@gmail.com", message_id="<r@acme>", from_addr="jane.doe@acme.com",
            from_domain="acme.com", company="Acme", signal="recruiter",
            subject="About your application", date="2026-07-01T10:00:00").ensure_id())
        domain, contacts = outreach.discover_company_contacts(
            load_config(None), store, "Acme", url="https://acme.com", fetch=True)
        assert domain == "acme.com"
        emails = [c["email"] for c in contacts]
        assert contacts[0] == {"email": "jane.doe@acme.com", "confidence": "high",
                               "source": "recruiter", "note": "a recruiter emailed you from this address"}
        assert "careers@acme.com" in emails                        # published on-site (medium)
        assert any(c["source"] == "role_inbox" for c in contacts)  # role inboxes (low)


def test_scan_applied_contacts_persists_then_skips_fresh(monkeypatch):
    monkeypatch.setattr("jobscope.core.httpx.get_text", _fake_site)
    with _tmpstore() as store:
        _seed_app(store, "Acme", "applied", company_url="https://acme.com")
        stats = outreach.scan_applied_contacts(load_config(None), store, fetch=True)
        assert stats["discovered"] == 1 and stats["skipped"] == 0
        assert store.get_company_contacts("Acme")["domain"] == "acme.com"
        # a second scan skips the still-fresh company (no re-discovery)
        stats2 = outreach.scan_applied_contacts(load_config(None), store, fetch=True)
        assert stats2 == {"discovered": 0, "skipped": 1}
