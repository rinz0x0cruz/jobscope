"""Tests for the Gmail inbox tracker: deterministic rules, store round-trips,
the monotonic status machine, dedup, and an end-to-end IMAP sync with a fake
mailbox (no network)."""
import os
import tempfile
from email.message import EmailMessage

from jobscope.ingest import inbox, mailrules
from jobscope.core.config import load_config
from jobscope.core.model import Application, Job, MailEvent
from jobscope.core.store import Store


# --- helpers ----------------------------------------------------------------
def _store():
    tmp = tempfile.mkdtemp()
    return Store(os.path.join(tmp, "t.db"))


def _raw(from_, subject, body, msgid, date="Mon, 01 Jun 2026 10:00:00 +0000"):
    m = EmailMessage()
    m["From"] = from_
    m["Subject"] = subject
    m["Message-ID"] = msgid
    m["Date"] = date
    m.set_content(body)
    return m.as_bytes()


class FakeIMAP:
    """Minimal stand-in for imaplib.IMAP4_SSL driven by a class-level mailbox."""

    mailbox: dict[int, bytes] = {}
    instances: list["FakeIMAP"] = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.selected = None
        self.readonly = None
        self.logged_out = False
        FakeIMAP.instances.append(self)

    def login(self, user, pw):
        self.user = user
        return ("OK", [b"logged in"])

    def select(self, folder, readonly=False):
        self.selected = folder
        self.readonly = readonly
        return ("OK", [b"1"])

    def uid(self, command, *args):
        cmd = command.lower()
        if cmd == "search":
            ids = b" ".join(str(u).encode() for u in sorted(FakeIMAP.mailbox))
            return ("OK", [ids])
        if cmd == "fetch":
            uid = int(args[0])
            raw = FakeIMAP.mailbox.get(uid)
            if raw is None:
                return ("NO", [None])
            return ("OK", [(f"{uid} (UID {uid})".encode(), raw)])
        return ("OK", [None])

    def logout(self):
        self.logged_out = True
        return ("BYE", [b"bye"])


def _cfg(monkeypatch):
    monkeypatch.setenv("TEST_INBOX_PW", "app-password-123")
    cfg = load_config("__no_such_config_for_tests__.yaml")   # defaults, ignore ambient config.yaml
    cfg["inbox"]["enabled"] = True
    cfg["inbox"]["accounts"] = [{"email": "me@gmail.com", "password_env": "TEST_INBOX_PW"}]
    cfg["inbox"]["lookback_days"] = 365
    return cfg


# --- mailrules: classification precedence -----------------------------------
def test_classify_confirmation():
    assert mailrules.classify_signal(
        "no-reply@greenhouse.io", "Thank you for applying to Databricks",
        "We have received your application.") == "confirmation"


def test_classify_rejection_beats_interview():
    # A rejection email that also mentions "interview" must classify as rejection.
    assert mailrules.classify_signal(
        "x@lever.co", "Your application",
        "We enjoyed your interview but unfortunately will not be moving forward."
    ) == "rejection"


def test_classify_offer():
    assert mailrules.classify_signal(
        "x@ashbyhq.com", "Great news", "We are pleased to offer you the position."
    ) == "offer"


def test_classify_assessment():
    assert mailrules.classify_signal(
        "x@greenhouse.io", "Next step: coding challenge",
        "Please complete the online assessment on HackerRank.") == "assessment"


def test_classify_interview():
    assert mailrules.classify_signal(
        "x@hire.lever.co", "Interview scheduling",
        "We'd like to schedule a call. Share your availability.") == "interview"


def test_classify_other():
    assert mailrules.classify_signal("news@example.com", "Weekly newsletter", "Deals!") == "other"


# --- mailrules: weighted scoring + ambiguity gate ---------------------------
def test_score_signals_weights_subject_double():
    # A keyword in the subject counts double the same keyword in the body.
    assert mailrules.score_signals("Interview invitation", "")["interview"] >= 6
    assert mailrules.score_signals("", "we would like to schedule an interview")["interview"] >= 3


def test_classify_scored_clear_winner_not_ambiguous():
    top, _scores, ambiguous, _tied = mailrules.classify_scored(
        "Thank you for applying to Acme", "We have received your application.")
    assert top == "confirmation"
    assert ambiguous is False


def test_classify_scored_flags_tie_ambiguous():
    # Balanced assessment + interview evidence, no clear lead -> ambiguous tie.
    top, _scores, ambiguous, tied = mailrules.classify_scored(
        "Next round", "Please complete the coding challenge, then we will set up a chat.")
    assert ambiguous is True
    assert set(tied) >= {"assessment", "interview"}


def test_classify_scored_other_on_no_keywords():
    top, _scores, ambiguous, _tied = mailrules.classify_scored("Weekly newsletter", "Deals inside!")
    assert top == "other"
    assert ambiguous is False


def test_classify_scored_rejection_decisive_not_ambiguous():
    # A strong rejection is decisive even when the subject echoes "your application".
    top, _scores, ambiguous, _tied = mailrules.classify_scored(
        "Your application to Acme", "Unfortunately we will not be moving forward at this time.")
    assert top == "rejection"
    assert ambiguous is False


# --- mailrules: relevance gating --------------------------------------------
def test_is_job_related_by_domain():
    assert mailrules.is_job_related("greenhouse.io", "other") is True
    assert mailrules.is_job_related("boards.greenhouse.io", "other") is True  # ATS subdomain
    assert mailrules.is_job_related("linkedin.com", "other") is False         # job board needs a signal
    assert mailrules.is_job_related("linkedin.com", "confirmation") is True


def test_is_job_related_by_signal_only():
    assert mailrules.is_job_related("randomstartup.com", "rejection") is True
    assert mailrules.is_job_related("randomstartup.com", "recruiter") is False  # weak + unknown


def test_is_noise_sender():
    assert mailrules.is_noise_sender("Glassdoor Community", "noreply@glassdoor.com") is True
    assert mailrules.is_noise_sender("LinkedIn Job Alerts", "jobalerts-noreply@linkedin.com") is True
    assert mailrules.is_noise_sender("Databricks Recruiting", "no-reply@greenhouse.io") is False


# --- mailrules: parsing -----------------------------------------------------
def test_parse_company_role_from_subject():
    company, role = mailrules.parse_company_role(
        "Databricks Recruiting", "greenhouse.io",
        "Your application for the Security Engineer role at Databricks", "")
    assert company == "Databricks"
    assert "Security Engineer" in role


def test_parse_company_from_sender_display():
    company, _ = mailrules.parse_company_role(
        "Stripe", "hire.lever.co", "We received your application", "")
    assert company == "Stripe"


def test_parse_company_ignores_noreply_display():
    company, _ = mailrules.parse_company_role(
        "no-reply", "greenhouse.io", "Application to Acme received", "")
    assert company.lower() == "acme"


def test_parse_company_applying_to():
    company, _ = mailrules.parse_company_role(
        "no-reply", "greenhouse.io", "Thank you for applying to Sphera!", "")
    assert company.lower() == "sphera"


def test_parse_company_job_application_phrase():
    company, _ = mailrules.parse_company_role(
        "Careers", "myworkday.com", "We've received your Target job application", "")
    assert company.lower() == "target"


def test_normalize_company_strips_suffix():
    assert mailrules.normalize_company("Databricks, Inc.") == "databricks"
    assert mailrules.normalize_company("Acme Technologies LLC") == "acme"


# --- mailrules: subject authority + robust company parsing ------------------
def test_classify_confirmation_subject_beats_interview_body():
    # ATS "application received" confirmations pad the body with interview-ish
    # boilerplate ("next steps", "we'll invite you"); the subject must win.
    assert mailrules.classify_signal(
        "no-reply@darwinbox.in", "Application Received for Security Analyst",
        "Thanks for applying. Here are the next steps in the process and we will "
        "invite you to the next stage in due course.") == "confirmation"
    assert mailrules.classify_signal(
        "no-reply@zscaler.com", "Thank you for your application to Zscaler!",
        "We'll be in touch about next steps and may invite you to a conversation."
    ) == "confirmation"


def test_classify_interview_still_detected_from_subject():
    # A genuine interview invite (no confirmation subject) still classifies.
    assert mailrules.classify_signal(
        "x@greenhouse.io", "Invitation to interview",
        "We'd like to invite you to an interview.") == "interview"


def test_classify_rejection_still_wins_from_body():
    assert mailrules.classify_signal(
        "no-reply@ashbyhq.com", "Your application to Acme",
        "Unfortunately we will not be moving forward at this time.") == "rejection"


def test_parse_company_interest_in():
    company, _ = mailrules.parse_company_role(
        "Tide", "gh-mail.tide.co", "Thank you for your interest in Tide", "")
    assert company.lower() == "tide"


def test_parse_company_at_company_tail():
    # A long role prefix precedes the employer -- grab the trailing "at <Company>".
    company, _ = mailrules.parse_company_role(
        "no-reply", "myworkday.com",
        "Your application for R0000441842 Lead Engineer (CTI team) (Open) at Target",
        "")
    assert company == "Target"


def test_parse_company_at_company_with_pipe():
    company, _ = mailrules.parse_company_role(
        "no-reply", "example-relay.com",
        "Thank you for your application at MantleSolutions | 75 Security Analyst", "")
    assert company == "MantleSolutions"


def test_parse_company_from_direct_domain():
    # A direct employer domain is the company when the subject names none.
    company, _ = mailrules.parse_company_role(
        "Recruiting", "zscaler.com", "We received your application", "")
    assert company.lower() == "zscaler"


def test_parse_company_prefers_display_over_domain_acronym():
    # A real display name ("Millennium Recruiting Team") beats a bare domain
    # acronym (careers.mlp.com) when the subject names no company.
    company, _ = mailrules.parse_company_role(
        "Millennium Recruiting Team", "careers.mlp.com",
        "Mohit, we have received your application", "")
    assert company == "Millennium"


def test_parse_company_rejects_body_filler():
    # "application at this time" must never yield the company "this time".
    company, _ = mailrules.parse_company_role(
        "Careers", "greenhouse.io", "Update on your application",
        "Regarding your application at this time, we have no update.")
    assert company == ""


def test_parse_company_ignores_system_display():
    # A darwinbox "HRMS" system display over a relay domain is not a company.
    company, _ = mailrules.parse_company_role(
        "HRMS", "darwinbox.in", "Application Received for Analyst - L0", "")
    assert company == ""


# --- mailrules: status machine ----------------------------------------------
def test_signal_to_status():
    assert mailrules.signal_to_status("confirmation") == "applied"
    assert mailrules.signal_to_status("interview") == "interview"
    assert mailrules.signal_to_status("offer") == "offer"
    assert mailrules.signal_to_status("rejection") == "rejected"
    assert mailrules.signal_to_status("other") == ""


def test_advance_status_is_monotonic():
    assert mailrules.advance_status("applied", "interview") == "interview"
    assert mailrules.advance_status("offer", "applied") == "offer"      # never regress
    assert mailrules.advance_status("", "applied") == "applied"


def test_advance_status_rejection_is_terminal():
    assert mailrules.advance_status("interview", "rejected") == "rejected"
    assert mailrules.advance_status("rejected", "interview") == "rejected"


def test_best_company_match_fuzzy():
    cands = ["databricks", "stripe", "coinbase"]
    assert mailrules.best_company_match("Databricks, Inc.", cands) == "databricks"
    assert mailrules.best_company_match("Totally Unrelated Co", cands) is None


# --- store: mail_events + applications --------------------------------------
def test_upsert_mail_event_dedupes():
    store = _store()
    ev = MailEvent(account="me@x", message_id="<abc@x>", subject="Hi", signal="confirmation",
                   job_id="mail:1", company="Acme")
    assert store.upsert_mail_event(ev) is True
    assert store.upsert_mail_event(ev) is False              # same id -> no-op
    assert len(store.mail_events()) == 1
    assert len(store.mail_events("mail:1")) == 1
    assert store.mail_events("other") == []
    store.close()


def test_email_only_application_shows_company_title():
    store = _store()
    store.set_application(Application(job_id="mail:z", status="applied",
                                      company="Zeta", title="SRE", source="inbox"))
    apps = store.applications()
    assert apps[0]["company"] == "Zeta" and apps[0]["title"] == "SRE"
    store.close()


def test_applications_prefers_job_row_over_email_fallback():
    store = _store()
    j = Job(source="ats", title="Security Engineer", company="Databricks").ensure_id()
    store.upsert_job(j)
    store.set_application(Application(job_id=j.id, status="applied",
                                     company="WRONG", title="WRONG", source="inbox"))
    app = [a for a in store.applications() if a["job_id"] == j.id][0]
    assert app["company"] == "Databricks" and app["title"] == "Security Engineer"
    store.close()


# --- inbox: apply-to-application logic --------------------------------------
def test_apply_to_application_monotonic_and_terminal():
    store = _store()
    base = dict(account="me@x", company="Acme", role="Engineer", job_id="mail:a")
    inbox._apply_to_application(store, MailEvent(message_id="<1>", signal="offer", **base))
    assert store.get_application("mail:a")["status"] == "offer"
    inbox._apply_to_application(store, MailEvent(message_id="<2>", signal="confirmation", **base))
    assert store.get_application("mail:a")["status"] == "offer"        # no regress
    inbox._apply_to_application(store, MailEvent(message_id="<3>", signal="rejection", **base))
    assert store.get_application("mail:a")["status"] == "rejected"
    inbox._apply_to_application(store, MailEvent(message_id="<4>", signal="interview", **base))
    assert store.get_application("mail:a")["status"] == "rejected"     # terminal
    store.close()


def test_apply_preserves_prepared_package():
    store = _store()
    store.set_application(Application(job_id="mail:p", status="prepared",
                                     package_dir="/pkg", resume_path="/r.pdf"))
    inbox._apply_to_application(store, MailEvent(job_id="mail:p", signal="interview",
                                                 company="Acme", role="Eng"))
    app = store.get_application("mail:p")
    assert app["status"] == "interview"
    assert app["package_dir"] == "/pkg" and app["resume_path"] == "/r.pdf"
    store.close()


def test_link_job_matches_scraped_company():
    store = _store()
    j = Job(source="ats", title="SE", company="Databricks").ensure_id()
    store.upsert_job(j)
    index = {mailrules.normalize_company(job.company): job.id
             for job in store.jobs(order_by_score=False) if job.company}
    assert inbox._link_job("Databricks, Inc.", "SE", index) == j.id      # linked
    assert inbox._link_job("Unknown Co", "SE", index).startswith("mail:")  # synthetic
    store.close()


# --- inbox: end-to-end IMAP sync (fake mailbox) -----------------------------
def _load_mailbox():
    FakeIMAP.mailbox = {
        1: _raw("Databricks Recruiting <no-reply@greenhouse.io>",
                "Thank you for applying to Databricks",
                "We have received your application.", "<db-1@greenhouse.io>"),
        2: _raw("Stripe <no-reply@hire.lever.co>", "Interview with Stripe",
                "We'd like to schedule a call. Please share your availability.",
                "<st-2@lever.co>"),
        3: _raw("Acme Careers <careers@acme-unknown-domain.com>",
                "Update on your application to Acme",
                "Unfortunately, we will not be moving forward with your application.",
                "<ac-3@acme.com>"),
        4: _raw("Deals <news@shopping-newsletter.com>", "50% off everything",
                "Buy now!", "<n-4@shop.com>"),
    }
    FakeIMAP.instances = []


def test_inbox_end_to_end(monkeypatch):
    _load_mailbox()
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)

    events = store.mail_events()
    assert len(events) == 3                                  # newsletter dropped
    signals = {e["company"].lower(): e["signal"] for e in events if e["company"]}
    assert signals.get("databricks") == "confirmation"
    assert signals.get("stripe") == "interview"

    statuses = {a["company"].lower(): a["status"] for a in store.applications() if a["company"]}
    assert statuses.get("databricks") == "applied"
    assert statuses.get("stripe") == "interview"
    assert statuses.get("acme") == "rejected"

    # Read-only mailbox: SELECT must have been issued with readonly=True.
    assert FakeIMAP.instances[0].readonly is True
    assert FakeIMAP.instances[0].logged_out is True
    store.close()


def test_inbox_is_incremental_and_idempotent(monkeypatch):
    _load_mailbox()
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)
    assert len(store.mail_events()) == 3

    # A second normal run advances past the UID watermark -> nothing new.
    inbox.run(cfg, store)
    assert len(store.mail_events()) == 3

    # A forced backfill re-scans every UID but message-id dedup keeps it a no-op.
    inbox.run(cfg, store, backfill=True)
    assert len(store.mail_events()) == 3
    store.close()


def test_inbox_dry_run_writes_nothing(monkeypatch):
    _load_mailbox()
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store, dry_run=True)
    assert store.mail_events() == []
    assert store.applications() == []
    assert store.meta_get("inbox:me@gmail.com:last_uid") is None  # watermark untouched
    store.close()


def test_inbox_disabled_is_noop():
    store = _store()
    cfg = load_config("__no_such_config_for_tests__.yaml")   # defaults: inbox.enabled == False
    assert inbox.run(cfg, store) == 0
    assert store.mail_events() == []
    store.close()
