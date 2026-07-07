"""Recruiter outreach (`jobscope outreach`) — offline, deterministic.

Covers the safe-by-construction contract: a contact is only ever an override, a
real recruiter address from your mail, or a role inbox on a *confirmed* domain
(never guessed); preview is the default; sending is deduped per company, honors
the do-not-contact list, and records the outreach.
"""
import os
import tempfile

from jobscope.apply import outreach
from jobscope.core.config import load_config
from jobscope.core.model import Job, MailEvent, Resume
from jobscope.core.store import Store, now_iso


def _seed(tmp, *, with_recruiter_mail=False, company_url="", do_not_contact=None):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
    cfg["email"]["enabled"] = True
    cfg["email"]["from_addr"] = "jane@example.com"
    cfg["email"]["to_addr"] = "jane@example.com"
    cfg["apply"]["outreach"]["enabled"] = True
    if do_not_contact is not None:
        cfg["apply"]["outreach"]["do_not_contact"] = do_not_contact

    store = Store(cfg["output"]["db_path"])
    store.save_resume(Resume(full_name="Jane Doe", email="jane@example.com",
                             skills=["python", "aws", "kubernetes"], seniority="senior",
                             years_experience=6.0), "default")
    # job.url is an ATS/board link (must NOT be used as the employer domain)
    job = Job(source="indeed", title="Security Engineer", company="Acme",
              company_url=company_url, url="https://boards.greenhouse.io/acme/jobs/1",
              description="We need python aws kubernetes and threat modeling.").ensure_id()
    store.upsert_job(job)
    if with_recruiter_mail:
        store.upsert_mail_event(MailEvent(
            account="jane@example.com", message_id="<r1@acme>", from_addr="talent@acme.com",
            from_domain="acme.com", subject="About your application", date="2026-07-01T10:00:00",
            signal="recruiter", job_id=job.id).ensure_id())
    return cfg, store, job


def test_resolve_override_wins():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp)
        t = outreach.resolve_target(cfg, store, job, override="hr@acme.com")
        assert t and t.email == "hr@acme.com" and t.source == "override" and t.confidence == "high"
        store.close()


def test_resolve_uses_real_recruiter_address():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp, with_recruiter_mail=True)
        t = outreach.resolve_target(cfg, store, job)
        assert t and t.email == "talent@acme.com" and t.source == "mail_event" and t.confidence == "high"
        store.close()


def test_resolve_role_inbox_only_on_confirmed_domain():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp, company_url="https://acme.com/careers")
        t = outreach.resolve_target(cfg, store, job)
        assert t and t.email == "careers@acme.com" and t.source == "role_inbox" and t.confidence == "low"
        store.close()


def test_resolve_never_fabricates_without_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp)  # no mail, no company_url; url is a board link
        assert outreach.resolve_target(cfg, store, job) is None
        store.close()


def test_draft_is_deterministic_and_grounded():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp)  # ai disabled by default -> deterministic
        resume = store.get_resume()
        target = outreach.Target(email="careers@acme.com", source="role_inbox",
                                 confidence="low", domain="acme.com")
        subject, body = outreach.build_draft(cfg, store, resume, job, target)
        assert "Jane Doe" in subject and "Security Engineer" in subject
        assert "attached" in body.lower() and ("résumé" in body.lower() or "resume" in body.lower())
        assert "python" in body.lower()  # a real matched skill, not invented
        store.close()


def test_dry_run_previews_without_sending(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp, with_recruiter_mail=True)
        rc = outreach.run(cfg, store, job.id, send=False)
        assert rc == 0
        assert sent == []  # nothing sent
        assert not (store.get_application(job.id) or {}).get("outreach_at")
        out = capsys.readouterr().out
        assert "talent@acme.com" in out and "dry-run" in out
        store.close()


def test_send_records_then_dedups(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp, with_recruiter_mail=True)
        rc = outreach.run(cfg, store, job.id, send=True)
        assert rc == 0 and len(sent) == 1 and sent[0]["to"] == "talent@acme.com"
        app = store.get_application(job.id)
        assert app["outreach_at"] and app["outreach_to"] == "talent@acme.com"
        # a second send for the same job is deduped (not re-sent)
        rc2 = outreach.run(cfg, store, job.id, send=True)
        assert rc2 == 0 and len(sent) == 1
        store.close()


def test_do_not_contact_blocks_send(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp, with_recruiter_mail=True, do_not_contact=["Acme"])
        rc = outreach.run(cfg, store, job.id, send=True)
        assert rc == 1 and sent == []
        store.close()


def test_cooldown_blocks_same_company(monkeypatch):
    sent = []
    monkeypatch.setattr("jobscope.deliver.email.send", lambda *a, **k: sent.append(k) or True)
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store, job = _seed(tmp, with_recruiter_mail=True)
        # another Acme role already contacted just now -> cooldown covers the company
        job2 = Job(source="indeed", title="AppSec Engineer", company="Acme",
                   description="python aws").ensure_id()
        store.upsert_job(job2)
        store.mark_outreach(job2.id, "careers@acme.com", now_iso())
        rc = outreach.run(cfg, store, job.id, send=True)
        assert rc == 0 and sent == []
        store.close()
