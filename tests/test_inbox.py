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
    """Minimal stand-in for imaplib.IMAP4_SSL. ``mailbox`` is INBOX; ``mailboxes``
    holds any extra folders (e.g. "[Gmail]/Spam") for multi-folder tests."""

    mailbox: dict[int, bytes] = {}
    mailboxes: dict[str, dict[int, bytes]] = {}
    instances: list["FakeIMAP"] = []
    uidvalidity: int | None = 1

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.selected = None
        self.readonly = None
        self.logged_out = False
        self.uid_calls = []
        self._cur = FakeIMAP.mailbox
        FakeIMAP.instances.append(self)

    def login(self, user, pw):
        self.user = user
        return ("OK", [b"logged in"])

    def select(self, folder, readonly=False):
        self.selected = folder
        self.readonly = readonly
        key = (folder or "").strip('"')
        if key == "INBOX":
            self._cur = FakeIMAP.mailbox
        elif key in FakeIMAP.mailboxes:
            self._cur = FakeIMAP.mailboxes[key]
        else:
            return ("NO", [b"no such folder"])
        return ("OK", [str(len(self._cur)).encode()])

    def uid(self, command, *args):
        self.uid_calls.append((command.lower(), args))
        cmd = command.lower()
        if cmd == "search":
            ids = b" ".join(str(u).encode() for u in sorted(self._cur))
            return ("OK", [ids])
        if cmd == "fetch":
            uid = int(args[0])
            raw = self._cur.get(uid)
            if raw is None:
                return ("NO", [None])
            return ("OK", [(f"{uid} (UID {uid})".encode(), raw)])
        return ("OK", [None])

    def response(self, name):
        if name.upper() == "UIDVALIDITY":
            value = FakeIMAP.uidvalidity
        elif name.upper() == "UIDNEXT":
            value = max(self._cur, default=0) + 1
        else:
            value = None
        return (name.upper(), [str(value).encode()] if value is not None else [None])

    def logout(self):
        self.logged_out = True
        return ("BYE", [b"bye"])


def setup_function():
    FakeIMAP.uidvalidity = 1


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


def test_ack_with_interview_boilerplate_is_confirmation():
    # Real Accenture Workday acknowledgment (curly apostrophes): the subject is a
    # confirmation and the body is an application-received note that merely mentions
    # "interview" + a day/time in boilerplate -- it must NOT read as an interview.
    assert mailrules.classify_signal(
        "accenture@myworkday.com",
        "It\u2019s great that you\u2019re interested in Accenture!",
        "Hi MOHIT, Thanks for applying for the role of Security Architect. We\u2019ll "
        "get started on carefully reviewing your application and keep you updated "
        "about next steps. Here you can track the status of your application. "
        "We can schedule an interview later; our team is available Monday 9am."
    ) == "confirmation"


def test_smart_quotes_do_not_break_matching():
    # Curly apostrophes must still match patterns written with straight quotes.
    assert mailrules.classify_signal(
        "careers@acme.com", "We\u2019re glad you\u2019re interested in Acme",
        "Thanks for applying.") == "confirmation"


def test_verification_code_is_transactional():
    assert mailrules.is_transactional("Verification Code - Accenture", "Your code is: 027236")
    assert mailrules.is_transactional("Verify your email address", "")
    assert mailrules.is_transactional("Reset your password", "")
    # a leading "Security code ..." OTP (no "your" prefix) is transactional -> dropped
    assert mailrules.is_transactional("Security code for your application to CloudSEK", "")
    assert mailrules.is_transactional("Security code: 483920", "")
    assert not mailrules.is_transactional(
        "Interview invitation", "Please share your availability for a call.")
    # a real security-role application must NOT be dropped as transactional
    assert not mailrules.is_transactional("Application received for Security Engineer", "")


def test_real_interview_still_classifies_as_interview():
    # A genuine interview invite must remain an interview after the ack fixes.
    assert mailrules.classify_signal(
        "recruiter@acme.com", "Interview invitation - Security Engineer",
        "We\u2019d like to schedule an interview. Please share your availability."
    ) == "interview"


def test_classify_rejection_beats_interview():
    # A rejection email that also mentions "interview" must classify as rejection.
    assert mailrules.classify_signal(
        "x@lever.co", "Your application",
        "We enjoyed your interview but unfortunately will not be moving forward."
    ) == "rejection"


def test_classify_confirmation_over_conditional_not_selected():
    # An application-RECEIVED acknowledgment that mentions a *conditional* "if you
    # are not selected, keep an eye on our jobs page" must stay a confirmation --
    # the hypothetical "not selected" is dropped before rejection scoring.
    assert mailrules.classify_signal(
        "no-reply@hire.lever.co",
        "Thank you for your application to Drivetrain",
        "Thank you for your interest in Drivetrain! We received your application "
        "for Security Engineer. If you are not selected for this position, keep an "
        "eye on our jobs page as we're growing.") == "confirmation"


def test_classify_confirmation_over_conditional_dont_hear():
    # "If you don't hear from us ... you were not a fit" is a conditional future in
    # an acknowledgment (Workday auto-reply), not a real rejection.
    assert mailrules.classify_signal(
        "no-reply@myworkday.com",
        "Thanks for your application!",
        "Thank you for taking the time to apply for the Analyst role. Your "
        "application will be reviewed by our team, and if your experience matches "
        "the requirements, we'll be in touch. If you don't hear from us in the next "
        "four weeks it's likely that you were not a fit for this role.") == "confirmation"


def test_classify_rejection_with_confirmation_padding():
    # A real rejection ("we've decided not to move forward") that opens with
    # confirmation padding ("Thank you for your interest ... for taking the time to
    # apply") and a confirmation-ish subject must still read as a rejection -- the
    # decision is stated unconditionally, so de-conditionalization keeps it.
    assert mailrules.classify_signal(
        "no-reply@us.greenhouse-mail.io",
        "Update on your application to Endor Labs",
        "Thank you for your interest in Endor Labs and for taking the time to "
        "apply. After careful review, we've decided not to move forward with your "
        "application at this time. We wish you all the best.") == "rejection"


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


# --- inbox: quorum tie-break wiring (gated, deterministic fallback) ----------
def test_quorum_pick_returns_none_when_ai_unavailable(monkeypatch):
    # Tie-break is gated: with AI/quorum off, the deterministic label stands.
    from jobscope.core import ai
    monkeypatch.setattr(ai, "available", lambda cfg: False)
    assert inbox._quorum_pick({}, None, "Next round", "body", ["assessment", "interview"]) is None


def test_quorum_pick_needs_two_candidates(monkeypatch):
    # A lone candidate is not a tie, so the AI layer is never consulted.
    from jobscope.core import ai
    seen = {"chat": False}

    def _chat(*a, **k):
        seen["chat"] = True
        return "interview"

    monkeypatch.setattr(ai, "available", lambda cfg: True)
    monkeypatch.setattr(ai, "chat", _chat)
    assert inbox._quorum_pick({}, None, "s", "b", ["interview"]) is None
    assert seen["chat"] is False


def test_quorum_pick_arbitrates_only_among_tied(monkeypatch):
    # Quorum may choose a tied label (case/punctuation-tolerant) but never one outside the set.
    from jobscope.core import ai
    monkeypatch.setattr(ai, "available", lambda cfg: True)
    monkeypatch.setattr(ai, "strategy_for", lambda cfg, task: "ensemble")

    monkeypatch.setattr(ai, "chat", lambda *a, **k: "Interview.")
    assert inbox._quorum_pick({}, None, "s", "b", ["assessment", "interview"]) == "interview"

    monkeypatch.setattr(ai, "chat", lambda *a, **k: "offer")  # outside the tied set -> rejected
    assert inbox._quorum_pick({}, None, "s", "b", ["assessment", "interview"]) is None


def test_quorum_pick_none_when_ai_returns_nothing(monkeypatch):
    # An empty/None AI response falls back to the deterministic label.
    from jobscope.core import ai
    monkeypatch.setattr(ai, "available", lambda cfg: True)
    monkeypatch.setattr(ai, "strategy_for", lambda cfg, task: "ensemble")
    monkeypatch.setattr(ai, "chat", lambda *a, **k: None)
    assert inbox._quorum_pick({}, None, "s", "b", ["assessment", "interview"]) is None


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


def test_is_newsletter_domain():
    assert mailrules.is_newsletter_domain("substack.com") is True
    assert mailrules.is_newsletter_domain("email.mg1.substack.com") is True   # subdomain
    assert mailrules.is_newsletter_domain("medium.com") is True
    assert mailrules.is_newsletter_domain("thinkific.com") is True            # course platform
    assert mailrules.is_newsletter_domain("notify.thinkific.com") is True     # course-enrollment subdomain
    assert mailrules.is_newsletter_domain("eatclub.in") is True               # food-delivery receipts
    assert mailrules.is_newsletter_domain("leetcode.com") is True             # coding-practice platform
    assert mailrules.is_newsletter_domain("email.leetcode.com") is True       # marketing subdomain
    assert mailrules.is_newsletter_domain("educative.io") is True             # interactive-course platform
    assert mailrules.is_newsletter_domain("email.educative.io") is True       # course-promo subdomain
    assert mailrules.is_newsletter_domain("greenhouse.io") is False           # ATS, not a newsletter
    assert mailrules.is_newsletter_domain("zscaler.com") is False             # employer
    assert mailrules.is_newsletter_domain("") is False


def test_strip_html_drops_style_and_script():
    from jobscope.ingest.ats import _strip_html
    raw = ("<style>#outlook a { padding:0; } body { margin:0; }</style>"
           "<script>var x = 1;</script><!-- hidden --><p>Hi Mohit, "
           "thank you for applying.</p>")
    out = _strip_html(raw)
    assert out == "Hi Mohit, thank you for applying."
    assert "padding" not in out and "var x" not in out and "hidden" not in out


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


def test_successfactors_eu_is_ats_domain():
    # SAP SuccessFactors' EU data-center domain is an ATS relay, not an employer.
    assert mailrules.is_ats_domain("successfactors.eu") is True
    assert mailrules.domain_platform("system.successfactors.eu") == "successfactors"
    assert mailrules.company_from_domain("successfactors.eu") == ""


def test_parse_company_from_email_display_name():
    # A SuccessFactors relay whose display name embeds the employer domain
    # ("HR@Bayer.com") must resolve to the employer, not the ATS platform.
    company, _ = mailrules.parse_company_role(
        "HR@Bayer.com", "successfactors.eu", "Thank you for your application",
        "You\u2019ve applied for the position of Cyber Security Engineer with Bayer.")
    assert company == "Bayer"


def test_parse_company_strips_trailing_workday_platform():
    # Workday appends its platform name to the sender display ("NCR Voyix Workday");
    # the employer ("NCR Voyix", acronym preserved) must survive the strip.
    company, _ = mailrules.parse_company_role(
        "NCR Voyix Workday", "myworkday.com", "Thank You for Your Application!", "")
    assert company == "NCR Voyix"


def test_parse_company_from_workday_tenant_url():
    # A Workday confirmation with a generic subject / empty display resolves the
    # employer from the careers-URL tenant in the body.
    company, _ = mailrules.parse_company_role(
        "", "myworkday.com", "Thanks for your application!",
        "Thank you for taking the time to apply for the R6521 Associate Threat "
        "Response Analyst role. https://mimecast.wd5.myworkdayjobs.com/Mimecast-Careers")
    assert company == "Mimecast"


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
    index = {}
    inbox._index_job(index, j.company, j.title, j.id)
    assert inbox._link_job("Databricks, Inc.", "SE", index) == j.id      # linked
    assert inbox._link_job("Unknown Co", "SE", index).startswith("mail:")  # synthetic
    store.close()


def _seed_sent_campaign(store, *, domain="acme.com", sent_at="2026-06-01T09:00:00Z"):
    campaign = store.create_outreach_campaign("Reply tracking", 1)
    target = store.upsert_outreach_campaign_target(
        campaign["id"], "Acme", "acme", rank_score=80,
    )
    contacts = [{"email": f"recruiter@{domain}", "source": "hunter",
                 "confidence": "medium", "note": "recruiter"}]
    store.set_outreach_campaign_contacts(
        target["id"], domain=domain, contacts=contacts, state="draft",
    )
    store.set_outreach_campaign_draft(
        target["id"], domain=domain, contacts=contacts,
        selected_email=f"recruiter@{domain}", subject="Hello", body="Body",
    )
    store.approve_outreach_campaign_target(target["id"])
    assert store.claim_outreach_campaign_target_send(target["id"])
    store.mark_outreach_campaign_target_sent(target["id"], sent_at)
    return target["id"]


def test_inbox_keeps_generic_reply_from_sent_campaign_domain(monkeypatch):
    FakeIMAP.mailbox = {
        1: _raw("Alex <alex@acme.com>", "Re: Hello",
                "Thanks for reaching out. Can we speak tomorrow?", "<reply@acme.com>"),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    cfg = _cfg(monkeypatch)
    store = _store()
    target_id = _seed_sent_campaign(store)

    assert inbox.run(cfg, store) == 0
    events = store.mail_events()

    assert len(events) == 1 and events[0]["signal"] == "campaign_reply"
    assert store.get_application(events[0]["job_id"]) is None
    from jobscope.apply import campaigns
    assert campaigns.reconcile_replies(store) == {"replied": 1, "opted_out": 0}
    assert store.get_outreach_campaign_target(target_id)["state"] == "replied"
    store.close()


def test_inbox_keeps_campaign_optout_without_storing_body(monkeypatch):
    FakeIMAP.mailbox = {
        1: _raw("Alex <alex@acme.com>", "Re: Hello",
                "Please do not contact me again.", "<stop@acme.com>"),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    cfg = _cfg(monkeypatch)
    cfg["inbox"]["store_snippets"] = False
    store = _store()
    target_id = _seed_sent_campaign(store)

    assert inbox.run(cfg, store) == 0
    event = store.mail_events()[0]

    assert event["signal"] == "campaign_optout" and event["snippet"] == ""
    from jobscope.apply import campaigns
    assert campaigns.reconcile_replies(store) == {"replied": 0, "opted_out": 1}
    assert store.get_outreach_campaign_target(target_id)["state"] == "opted_out"
    assert store.is_outreach_suppressed("domain", "acme.com")
    store.close()


def test_inbox_fetches_generic_subject_body_from_known_employer(monkeypatch):
    FakeIMAP.mailbox = {
        1: _raw(
            "Acme Recruiter <recruiter@acme.com>", "Next steps",
            "We would like to schedule a video interview. Please share your availability.",
            "<next-steps@acme.com>",
        ),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    cfg = _cfg(monkeypatch)
    store = _store()
    job = Job(
        source="ats", title="Security Engineer", company="Acme",
        location="Remote", url="https://acme.com/jobs/1",
    ).ensure_id()
    store.upsert_job(job)

    assert inbox.run(cfg, store) == 0

    events = store.mail_events(job.id)
    assert len(events) == 1 and events[0]["signal"] == "interview"
    assert store.get_application(job.id)["status"] == "interview"
    assert any(
        call[0] == "fetch" and "BODY.PEEK[]" in str(call[1])
        for call in FakeIMAP.instances[0].uid_calls
    )
    store.close()


def test_inbox_fetches_generic_followup_after_discovering_employer_in_same_scan(monkeypatch):
    FakeIMAP.mailbox = {
        1: _raw(
            "IBM Talent Acquisition <talent@ibm.com>",
            "You have successfully submitted your IBM job application - 124720 - "
            "Security Analyst Level 2 - SIEM & SOAR",
            "Thank you for applying to IBM.", "<ibm-confirm@ibm.com>",
        ),
        2: _raw(
            "IBM Talent Acquisition <talent@ibm.com>", "Your IBM Application: Next Steps",
            "Ref: 124720 - Security Analyst Level 2 - SIEM & SOAR Dear Mohit, "
            "please complete the online assessment.", "<ibm-next@ibm.com>",
        ),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    cfg = _cfg(monkeypatch)
    store = _store()

    assert inbox.run(cfg, store) == 0

    events = store.mail_events()
    assert [event["signal"] for event in events] == ["confirmation", "assessment"]
    assert {event["role"] for event in events} == {
        "Security Analyst Level 2 - SIEM & SOAR",
    }
    assert len({event["job_id"] for event in events}) == 1
    store.close()


def test_inbox_keeps_concurrent_ibm_requisitions_separate(monkeypatch):
    FakeIMAP.mailbox = {
        1: _raw(
            "IBM Talent Acquisition <talent@ibm.com>",
            "You have successfully submitted your IBM job application - 124720 - "
            "Security Analyst Level 2 - SIEM & SOAR",
            "Thank you for applying to IBM.", "<ibm-124720@ibm.com>",
        ),
        2: _raw(
            "IBM Talent Acquisition <talent@ibm.com>",
            "You have successfully submitted your IBM job application - 124835 - "
            "Security Consultant-SOC(XSIAM)",
            "Thank you for applying to IBM.", "<ibm-124835@ibm.com>",
        ),
        3: _raw(
            "IBM Talent Acquisition <talent@ibm.com>", "Your IBM Application: Next Steps",
            "Ref: 124835 - Security Consultant-SOC(XSIAM) Dear Mohit, "
            "please complete the online assessment.", "<ibm-next-124835@ibm.com>",
        ),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    cfg = _cfg(monkeypatch)
    store = _store()

    assert inbox.run(cfg, store) == 0

    events = store.mail_events()
    by_role = {}
    for event in events:
        by_role.setdefault(event["role"], set()).add(event["job_id"])
    assert set(by_role) == {
        "Security Analyst Level 2 - SIEM & SOAR",
        "Security Consultant-SOC(XSIAM)",
    }
    assert all(len(job_ids) == 1 for job_ids in by_role.values())
    assert len({event["job_id"] for event in events}) == 2
    applications = {app["title"]: app["status"] for app in store.applications()}
    assert applications == {
        "Security Analyst Level 2 - SIEM & SOAR": "applied",
        "Security Consultant-SOC(XSIAM)": "interview",
    }
    store.close()


def test_inbox_drops_generic_unknown_sender_without_fetching_body(monkeypatch):
    FakeIMAP.mailbox = {
        1: _raw(
            "Unknown <person@untracked-example.com>", "Next steps",
            "We would like to schedule a video interview. Please share your availability.",
            "<unknown-next-steps@example.com>",
        ),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    cfg = _cfg(monkeypatch)
    store = _store()

    assert inbox.run(cfg, store) == 0

    assert store.mail_events() == []
    assert not any(
        call[0] == "fetch" and "BODY.PEEK[]" in str(call[1])
        for call in FakeIMAP.instances[0].uid_calls
    )
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
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    FakeIMAP.uidvalidity = 1


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
    assert store.meta_get("inbox:me@gmail.com:uidvalidity") == "1"

    # A second normal run advances past the UID watermark -> nothing new.
    inbox.run(cfg, store)
    assert len(store.mail_events()) == 3

    # A forced backfill re-scans + re-scores every UID; message-id dedup keeps the
    # row count stable (it updates signals in place rather than inserting).
    inbox.run(cfg, store, backfill=True)
    assert len(store.mail_events()) == 3
    store.close()


def test_inbox_reconnects_after_transient_abort(monkeypatch):
    _load_mailbox()

    class FlakyIMAP(FakeIMAP):
        def uid(self, command, *args):
            if command.lower() == "search" and len(FakeIMAP.instances) == 1:
                raise inbox.imaplib.IMAP4.abort("connection reset")
            return super().uid(command, *args)

    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FlakyIMAP)
    monkeypatch.setattr(inbox.time, "sleep", lambda _seconds: None)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)

    assert len(FakeIMAP.instances) == 2
    assert len(store.mail_events()) == 3
    health = store.source_health("inbox:me@gmail.com")[0]
    assert health["status"] == "recovered" and health["attempts"] == 2
    store.close()


def test_failed_uid_search_does_not_advance_watermark(monkeypatch):
    _load_mailbox()

    class SearchFailureIMAP(FakeIMAP):
        def uid(self, command, *args):
            if command.lower() == "search":
                return ("NO", [b"temporary failure"])
            return super().uid(command, *args)

    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", SearchFailureIMAP)
    monkeypatch.setattr(inbox.time, "sleep", lambda _seconds: None)
    store = _store()
    cfg = _cfg(monkeypatch)
    cfg["inbox"]["imap_attempts"] = 1

    assert inbox.run(cfg, store) == 1
    assert store.meta_get("inbox:me@gmail.com:last_uid") is None
    assert store.meta_get("inbox:me@gmail.com:uidvalidity") is None
    store.close()


def test_failed_message_fetch_replays_without_advancing_watermark(monkeypatch):
    _load_mailbox()

    class FetchFailureIMAP(FakeIMAP):
        fail = True

        def uid(self, command, *args):
            if command.lower() == "fetch" and self.fail:
                return ("NO", [b"temporary failure"])
            return super().uid(command, *args)

    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FetchFailureIMAP)
    monkeypatch.setattr(inbox.time, "sleep", lambda _seconds: None)
    store = _store()
    cfg = _cfg(monkeypatch)
    cfg["inbox"]["imap_attempts"] = 1

    assert inbox.run(cfg, store) == 1
    assert store.meta_get("inbox:me@gmail.com:last_uid") is None
    FetchFailureIMAP.fail = False
    assert inbox.run(cfg, store) == 0
    assert len(store.mail_events()) == 3
    assert store.meta_get("inbox:me@gmail.com:last_uid") == "4"
    store.close()


def test_classification_reads_beyond_legacy_1500_chars(monkeypatch):
    filler = "status update " * 150
    FakeIMAP.mailbox = {
        1: _raw(
            "Acme Recruiting <no-reply@greenhouse.io>", "Application update",
            filler + " We are pleased to offer you the Security Engineer position.",
            "<long-offer@greenhouse.io>",
        ),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)

    assert store.mail_events()[0]["signal"] == "offer"
    assert store.mail_events()[0]["snippet"] == ""
    store.close()


def test_uidvalidity_change_uses_bounded_recovery(monkeypatch):
    _load_mailbox()
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)
    cfg["inbox"]["uid_recovery_days"] = 14
    inbox.run(cfg, store)

    FakeIMAP.uidvalidity = 2
    FakeIMAP.mailbox = {
        1: _raw("Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme",
                "We received your application.", "<new-epoch@greenhouse.io>"),
    }
    inbox.run(cfg, store)

    assert store.meta_get("inbox:me@gmail.com:uidvalidity") == "2"
    assert store.meta_get("inbox:me@gmail.com:last_uid") == "1"
    health = store.source_health("inbox:me@gmail.com:INBOX")[0]
    assert health["status"] == "recovered"
    assert "last 14 day(s)" in health["detail"]
    search_args = FakeIMAP.instances[-1].uid_calls[0][1]
    assert "SINCE" in search_args
    store.close()


def test_uidvalidity_change_recovers_empty_folder_without_uidnext(monkeypatch):
    _load_mailbox()
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)
    inbox.run(cfg, store)

    class NoUidNextIMAP(FakeIMAP):
        def response(self, name):
            if name.upper() == "UIDNEXT":
                return ("UIDNEXT", [None])
            return super().response(name)

    FakeIMAP.uidvalidity = 2
    FakeIMAP.mailbox = {}
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", NoUidNextIMAP)

    assert inbox.run(cfg, store) == 0
    assert store.meta_get("inbox:me@gmail.com:uidvalidity") == "2"
    assert store.meta_get("inbox:me@gmail.com:last_uid") == "0"

    FakeIMAP.mailbox = {
        1: _raw("Acme <no-reply@greenhouse.io>", "Thank you for applying to Acme",
                "We received your application.", "<after-empty@greenhouse.io>"),
    }
    assert inbox.run(cfg, store) == 0
    assert any(event["message_id"] == "<after-empty@greenhouse.io>"
               for event in store.mail_events())
    store.close()


def test_raised_imap_fetch_error_does_not_advance_watermark(monkeypatch):
    _load_mailbox()

    class RaisedFetchFailureIMAP(FakeIMAP):
        def uid(self, command, *args):
            if command.lower() == "fetch":
                raise inbox.imaplib.IMAP4.error("server unavailable")
            return super().uid(command, *args)

    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", RaisedFetchFailureIMAP)
    monkeypatch.setattr(inbox.time, "sleep", lambda _seconds: None)
    store = _store()
    cfg = _cfg(monkeypatch)
    cfg["inbox"]["imap_attempts"] = 1

    assert inbox.run(cfg, store) == 1
    assert store.meta_get("inbox:me@gmail.com:last_uid") is None
    assert store.meta_get("inbox:me@gmail.com:uidvalidity") is None
    store.close()


def test_missing_uidvalidity_does_not_advance_watermark(monkeypatch):
    _load_mailbox()
    FakeIMAP.uidvalidity = None
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    assert inbox.run(cfg, store) == 1

    assert store.mail_events() == []
    assert store.meta_get("inbox:me@gmail.com:last_uid") is None
    health = store.source_health("inbox:me@gmail.com:INBOX")[0]
    assert health["status"] == "error"
    store.close()


def test_backfill_rescores_existing_events(monkeypatch):
    # Backfill re-scores already-stored events from their freshly-fetched bodies,
    # so a classifier change heals an old mis-tag in place (row count unchanged).
    FakeIMAP.mailbox = {
        1: _raw("Acme Careers <no-reply@acme-employer.com>",
                "Thank you for applying to Acme",
                "We have received your application and will review it.", "<ac-1@acme.com>"),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)
    evs = store.mail_events()
    assert len(evs) == 1 and evs[0]["signal"] == "confirmation"

    # Simulate an older rule having stored the wrong signal, then heal via backfill.
    store.update_mail_event(evs[0]["id"], signal="interview")
    assert store.mail_events()[0]["signal"] == "interview"

    inbox.run(cfg, store, backfill=True)
    healed = store.mail_events()
    assert len(healed) == 1                        # re-scored in place, no duplicate
    assert healed[0]["signal"] == "confirmation"   # mis-tag corrected from the fresh body
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


def test_inbox_drops_newsletter_domain(monkeypatch):
    # A newsletter whose subject collides with a lifecycle keyword ("Coding
    # Challenge" -> assessment) must be dropped by sender domain, never reaching
    # the funnel -- even though the assessment signal is otherwise "job-related".
    FakeIMAP.mailbox = {
        1: _raw("John Crickett from Coding Challenges <codingchallenges@substack.com>",
                "Coding Challenge #125 - Online Diff Viewer",
                "This week's challenge: build an online diff viewer.", "<cc-125@substack.com>"),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)

    assert store.mail_events() == []        # dropped up front, no event stored
    assert store.applications() == []       # and never advanced any application
    store.close()


def test_inbox_drops_course_and_consumer_domains(monkeypatch):
    # A Thinkific course "Training & Assessment" enrollment (-> assessment) and an
    # Eatclub food "order confirmation" both score otherwise-strong signals, but
    # come from non-job domains and must be dropped -- never landing in Interview.
    FakeIMAP.mailbox = {
        1: _raw("PURSUIT Academy <no-reply@notify.thinkific.com>",
                "You are now enrolled in PURSUIT - Volunteer Training & Assessment!",
                "Welcome! Thank you for enrolling in the training course.", "<enr-1@thinkific.com>"),
        2: _raw("Eatclub <orders@eatclub.in>",
                "Eatclub Confirmation - You have successfully paid online for your order",
                "Thank You for ordering with Eatclub. ORDER STATUS ORDER SUMMARY.", "<ord-1@eatclub.in>"),
    }
    FakeIMAP.mailboxes = {}
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)

    inbox.run(cfg, store)

    assert store.mail_events() == []
    assert store.applications() == []
    store.close()


def test_folders_for_default_and_spam():
    assert inbox._folders_for({}) == ["INBOX"]
    assert inbox._folders_for({"folder": "INBOX"}) == ["INBOX"]
    assert inbox._folders_for({"include_spam": True}) == ["INBOX", "[Gmail]/Spam"]
    assert inbox._folders_for({"include_spam": True, "spam_folder": "Junk"}) == ["INBOX", "Junk"]
    # include_spam off -> spam never scanned
    assert inbox._folders_for({"include_spam": False}) == ["INBOX"]


def test_uid_marker_inbox_uses_legacy_key():
    # INBOX keeps the pre-multi-folder key so existing watermarks stay valid.
    assert inbox._uid_marker("me@x.com", "INBOX") == "inbox:me@x.com:last_uid"
    assert inbox._uid_marker("me@x.com", "[Gmail]/Spam") == "inbox:me@x.com:[Gmail]/Spam:last_uid"
    assert inbox._uidvalidity_marker("me@x.com", "INBOX") == "inbox:me@x.com:uidvalidity"


def test_inbox_scans_spam_folder_when_enabled(monkeypatch):
    # A real application email Gmail misfiled into Spam is picked up when
    # inbox.include_spam is set -- in addition to everything in INBOX.
    FakeIMAP.mailbox = {
        1: _raw("Databricks <no-reply@greenhouse.io>", "Thank you for applying to Databricks",
                "We have received your application.", "<db-1@greenhouse.io>"),
    }
    FakeIMAP.mailboxes = {
        "[Gmail]/Spam": {
            5: _raw("Stripe <no-reply@hire.lever.co>", "Interview with Stripe",
                    "We'd like to schedule a call. Please share your availability.",
                    "<st-5@lever.co>"),
        }
    }
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)
    cfg["inbox"]["include_spam"] = True

    inbox.run(cfg, store)

    sigs = {e["company"].lower(): e["signal"] for e in store.mail_events() if e["company"]}
    assert sigs.get("databricks") == "confirmation"   # from INBOX
    assert sigs.get("stripe") == "interview"          # rescued from [Gmail]/Spam
    store.close()


def test_inbox_skips_spam_folder_by_default(monkeypatch):
    # With include_spam off (default), the spam folder is never opened.
    FakeIMAP.mailbox = {}
    FakeIMAP.mailboxes = {
        "[Gmail]/Spam": {
            5: _raw("Stripe <no-reply@hire.lever.co>", "Interview with Stripe",
                    "We'd like to schedule a call.", "<st-5@lever.co>"),
        }
    }
    FakeIMAP.instances = []
    monkeypatch.setattr(inbox.imaplib, "IMAP4_SSL", FakeIMAP)
    store = _store()
    cfg = _cfg(monkeypatch)   # include_spam defaults False

    inbox.run(cfg, store)
    assert store.mail_events() == []          # spam folder left untouched
    store.close()
