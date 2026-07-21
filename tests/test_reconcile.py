"""Tests for funnel reconciliation (`ingest.reconcile`): instance-splitting +
conservative reclassify. Deterministic, offline."""
import os
import tempfile

import pytest

from jobscope.core.config import load_config
from jobscope.core.model import Application, Job, MailEvent
from jobscope.core.store import Store
from jobscope.ingest import inbox, reconcile


def _ev(store, uid, subject, signal, company, date, *, role="", job_id, snippet=""):
    ev = MailEvent(account="me@x.com", uid=str(uid), subject=subject, signal=signal,
                   company=company, role=role, date=date, job_id=job_id, snippet=snippet,
                   from_domain="x.com").ensure_id()
    store.upsert_mail_event(ev)
    return ev


def _store(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
    return cfg, Store(cfg["output"]["db_path"])


def _mk(signal, date, role=""):
    return {"signal": signal, "date": date, "role": role, "first_seen": date}


# --- split_instances --------------------------------------------------------
def test_split_sequential_reapply():
    evs = [_mk("confirmation", "2026-07-01"), _mk("rejection", "2026-07-03"),
           _mk("confirmation", "2026-07-10")]
    inst = reconcile.split_instances(evs)
    assert len(inst) == 2
    assert [e["signal"] for e in inst[0]] == ["confirmation", "rejection"]
    assert [e["signal"] for e in inst[1]] == ["confirmation"]


def test_split_concurrent_distinct_roles():
    evs = [_mk("confirmation", "2026-07-01", role="Analyst"),
           _mk("confirmation", "2026-07-01", role="Engineer"),
           _mk("rejection", "2026-07-05", role="Analyst")]
    inst = reconcile.split_instances(evs)
    assert len(inst) == 2
    # the Analyst instance is rejected; the Engineer instance stays open
    analyst = next(i for i in inst if any(e.get("role") == "Analyst" for e in i))
    engineer = next(i for i in inst if any(e.get("role") == "Engineer" for e in i))
    assert reconcile.fold_status(analyst) == "rejected"
    assert reconcile.fold_status(engineer) == "applied"


def test_split_single_applied_then_rejected():
    evs = [_mk("confirmation", "2026-07-01"), _mk("rejection", "2026-07-02")]
    inst = reconcile.split_instances(evs)
    assert len(inst) == 1
    assert reconcile.fold_status(inst[0]) == "rejected"


def test_fold_status_advances_forward():
    assert reconcile.fold_status([_mk("confirmation", "d")]) == "applied"
    assert reconcile.fold_status([_mk("confirmation", "d1"), _mk("interview", "d2")]) == "interview"
    assert reconcile.fold_status([_mk("offer", "d")]) == "offer"


# --- reclassify_signal ------------------------------------------------------
def test_reclassify_drops_transactional():
    assert reconcile.reclassify_signal(
        {"subject": "Verification Code - Accenture", "snippet": "Your code is 1234",
         "signal": "assessment"}) is None


def test_reclassify_downgrades_false_interview_to_confirmation():
    assert reconcile.reclassify_signal(
        {"subject": "It\u2019s great that you\u2019re interested in Accenture!",
         "snippet": "", "signal": "interview"}) == "confirmation"


def test_reclassify_keeps_real_interview():
    assert reconcile.reclassify_signal(
        {"subject": "Interview invitation", "snippet": "", "signal": "interview"}) == "interview"
    # a generic-subject interview (cue was in a body we no longer store) is NOT dropped
    assert reconcile.reclassify_signal(
        {"subject": "Next steps", "snippet": "", "signal": "interview"}) == "interview"


def test_reclassify_downgrades_false_offer_when_evidence_is_retained():
    assert reconcile.reclassify_signal({
        "subject": "Your summer offer is here",
        "snippet": "Get 30% off Premium Annual and prepare for interviews.",
        "signal": "offer",
    }) == "other"


def test_reclassify_keeps_offer_without_retained_body():
    assert reconcile.reclassify_signal({
        "subject": "Application update",
        "snippet": "",
        "signal": "offer",
    }) == "offer"


def test_reclassify_downgrades_offered_by_subject_without_body():
    assert reconcile.reclassify_signal({
        "subject": "Post Graduate Diploma in Management offered by Great Lakes",
        "snippet": "",
        "signal": "offer",
    }) == "other"


def test_reclassify_drops_newsletter_domain_event():
    # a LeetCode contest / interview-prep promo mis-tagged interview -> dropped by domain
    assert reconcile.reclassify_signal(
        {"subject": "Ace your interview with LeetCode", "snippet": "",
         "signal": "interview", "from_domain": "leetcode.com"}) is None
    # a real employer interview (non-newsletter domain) is untouched
    assert reconcile.reclassify_signal(
        {"subject": "Interview invitation", "snippet": "", "signal": "interview",
         "from_domain": "greenhouse.io"}) == "interview"


# --- recompute (end to end) -------------------------------------------------
def test_recompute_reapply_keeps_company_active():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        base = "mail:acme"
        _ev(store, 1, "Thanks for applying to Acme", "confirmation", "Acme", "2026-07-01", job_id=base)
        _ev(store, 2, "Update on your application", "rejection", "Acme", "2026-07-03", job_id=base)
        _ev(store, 3, "Thanks for applying to Acme", "confirmation", "Acme", "2026-07-10", job_id=base)
        stats = reconcile.recompute(store)
        assert stats["instances"] == 2
        statuses = {a["job_id"]: a["status"] for a in store.applications()}
        assert statuses.get("mail:acme") == "rejected"
        assert statuses.get("mail:acme#2") == "applied"      # the reapply stays active
        # the reapply event was re-linked to the new instance
        assert any(e["job_id"] == "mail:acme#2" for e in store.mail_events())
        store.close()


def test_recompute_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        base = "mail:beta"
        _ev(store, 1, "Thanks for applying", "confirmation", "Beta", "2026-07-01", job_id=base)
        _ev(store, 2, "Rejected", "rejection", "Beta", "2026-07-03", job_id=base)
        _ev(store, 3, "Thanks for applying", "confirmation", "Beta", "2026-07-10", job_id=base)
        first = reconcile.recompute(store)
        second = reconcile.recompute(store)
        assert first == second
        assert len({a["job_id"] for a in store.applications()}) == 2
        latest = store.reconciliation_runs()[0]
        assert latest["status"] == "completed"
        assert store.reconciliation_decisions(latest["id"]) == []
        store.close()


def test_reclassify_end_to_end_fixes_stuck_interview_and_drops_otp():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        base = "mail:acc"
        _ev(store, 1, "It\u2019s great that you\u2019re interested in Accenture!", "interview",
            "Accenture", "2026-07-02", job_id=base)
        _ev(store, 2, "Verification Code - Accenture", "assessment", "Accenture",
            "2026-07-02", job_id=base, snippet="Your code is 1234")
        stats = reconcile.reclassify(store)
        assert stats["dropped"] == 1 and stats["reclassified"] == 1
        statuses = {a["job_id"]: a["status"] for a in store.applications()}
        assert statuses.get("mail:acc") == "applied"          # was stuck at "interview"
        assert not any(e["signal"] == "assessment" for e in store.mail_events())
        runs = store.reconciliation_runs()
        assert len(runs) == 1 and runs[0]["action"] == "reclassify"
        assert runs[0]["reclassified_count"] == 1 and runs[0]["dropped_count"] == 1
        decision_types = {
            decision["decision_type"]
            for decision in store.reconciliation_decisions(runs[0]["id"])
        }
        assert {"signal_reclassified", "event_dropped"} <= decision_types
        store.close()


def test_reclassify_downgrades_jd_assessment_to_other_with_snippet():
    # A recruiter mail whose only "assessment" was a security-JD phrase ("gap
    # assessments") re-scores to "other"; with the body in hand, the demote is trusted.
    assert reconcile.reclassify_signal(
        {"subject": "Regarding your interest in SecOps maturity gap assessments role",
         "snippet": "Thanks for sharing your CV and for showing interest in this role.",
         "signal": "assessment",
         "from_domain": "connectedcareers.services.global.ntt"}) == "other"


def test_reclassify_keeps_stuck_assessment_without_snippet():
    # No stored body -> an "other" re-score is not trusted, so a stuck signal stays
    # (a real assessment whose cue lived in a dropped body must never vanish).
    assert reconcile.reclassify_signal(
        {"subject": "Regarding your interest in SecOps maturity gap assessments role",
         "snippet": "", "signal": "assessment"}) == "assessment"


def test_recompute_tombstones_orphaned_mail_app():
    # A "mail:" app whose events were all dropped (newsletter/OTP) must not linger
    # as a ghost funnel card (LeetCode / Educative course blasts, GitHub CI mail).
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        store.set_application(Application(job_id="mail:ghost", status="interview",
                                         company="LeetCode", source="inbox"))
        reconcile.recompute(store)   # no events exist for mail:ghost
        assert not any(a["job_id"] == "mail:ghost" for a in store.applications())
        hidden = store.get_application("mail:ghost", include_tombstoned=True)
        assert hidden["tombstone_reason"] == "orphan_mail_application"
        run = store.reconciliation_runs()[0]
        assert run["status"] == "completed" and run["tombstoned_count"] == 1
        decisions = store.reconciliation_decisions(run["id"])
        assert decisions[0]["decision_type"] == "application_tombstoned"
        assert decisions[0]["recoverable"] is True
        store.close()


def test_recompute_tombstones_inbox_offer_on_scraped_job_without_funnel_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        job = Job(
            source="linkedin", title="Information Security Analyst",
            company="Cyberr", url="https://example.test/cyberr-role",
        ).ensure_id()
        store.upsert_job(job)
        store.set_application(Application(
            job_id=job.id, status="offer", company="CYBERR", source="inbox",
        ))
        _ev(
            store, 1, "Welcome to Cyberr", "other", "Cyberr", "2026-07-13",
            job_id=job.id, snippet="The professional network built for cybersecurity.",
        )

        reconcile.recompute(store)

        assert store.get_application(job.id) is None
        hidden = store.get_application(job.id, include_tombstoned=True)
        assert hidden["tombstone_reason"] == "orphan_mail_application"
        assert store.get_job(job.id) is not None
        assert store.mail_events(job.id)[0]["signal"] == "other"
        store.close()


def test_recompute_keeps_non_offer_inbox_app_on_scraped_job_without_funnel_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        job = Job(
            source="linkedin", title="Information Security Analyst",
            company="Cyberr", url="https://example.test/cyberr-applied",
        ).ensure_id()
        store.upsert_job(job)
        store.set_application(Application(
            job_id=job.id, status="applied", company="CYBERR", source="inbox",
        ))
        _ev(
            store, 1, "Welcome to Cyberr", "other", "Cyberr", "2026-07-13",
            job_id=job.id,
        )

        reconcile.recompute(store)

        assert store.get_application(job.id)["status"] == "applied"
        store.close()


def test_recompute_failure_rolls_back_mutations_and_marks_run_failed(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        base = "mail:atomic"
        _ev(store, 1, "Thanks for applying", "confirmation", "Acme", "2026-07-01",
            job_id=base)
        _ev(store, 2, "Rejected", "rejection", "Acme", "2026-07-03", job_id=base)
        _ev(store, 3, "Thanks for applying", "confirmation", "Acme", "2026-07-10",
            job_id=base)
        original = store._set_application
        writes = 0

        def fail_second_write(*args, **kwargs):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise RuntimeError("injected reconciliation failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "_set_application", fail_second_write)

        with pytest.raises(RuntimeError, match="injected reconciliation failure"):
            reconcile.recompute(store)

        assert store.applications() == []
        assert {event["job_id"] for event in store.mail_events()} == {base}
        run = store.reconciliation_runs()[0]
        assert run["status"] == "failed" and run["error_code"] == "transaction_failed"
        assert store.reconciliation_decisions(run["id"]) == []
        store.close()


def test_recompute_keeps_non_mail_app_without_events():
    # A scraped/manual app (non-"mail:" id) is NOT email-derived, so it survives a
    # recompute even with no mail events linked to it.
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        store.set_application(Application(job_id="gh:acme:123", status="applied",
                                         company="Acme"))
        reconcile.recompute(store)
        assert any(a["job_id"] == "gh:acme:123" for a in store.applications())
        store.close()


def test_recompute_merges_same_company_role_into_unambiguous_scraped_job():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        try:
            scraped = Job(
                source="ats", title="Security Analyst Level 2 - SIEM & SOAR",
                company="IBM", url="https://ibm.example/jobs/124720",
            ).ensure_id()
            store.upsert_job(scraped)
            legacy = "mail:legacy-ibm"
            store.set_application(Application(
                job_id=legacy, status="interview", company="IBM",
                title=scraped.title, source="inbox",
            ))
            _ev(store, 1, "IBM application submitted", "confirmation", "IBM",
                "2026-07-08", role=scraped.title, job_id=legacy)
            _ev(store, 2, "IBM assessment", "assessment", "IBM",
                "2026-07-09", role=scraped.title, job_id=legacy)
            _ev(store, 3, "IBM application status", "rejection", "IBM",
                "2026-07-14", role=scraped.title, job_id=scraped.id)

            reconcile.recompute(store)

            active = [app for app in store.applications() if app["company"] == "IBM"]
            assert [(app["job_id"], app["status"]) for app in active] == [
                (scraped.id, "rejected"),
            ]
            assert {event["job_id"] for event in store.mail_events()} == {scraped.id}
            hidden = store.get_application(legacy, include_tombstoned=True)
            assert hidden["tombstone_reason"] == "orphan_mail_application"
        finally:
            store.close()


def test_recompute_merges_single_requisition_into_stable_mail_application():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        try:
            role = "Security Consultant-SOC(XSIAM)"
            legacy = "mail:legacy-ibm"
            canonical = inbox._link_job("IBM", role, {})
            store.set_application(Application(
                job_id=legacy, status="interview", company="IBM",
                title=role, source="inbox",
            ))
            store.set_application(Application(
                job_id=canonical, status="rejected", company="IBM",
                title=role, source="inbox",
            ))
            _ev(store, 1, f"IBM application submitted - 124835 - {role}",
                "confirmation", "IBM", "2026-07-08", role=role, job_id=legacy)
            _ev(store, 2, f"IBM assessment - 124835 - {role}", "assessment", "IBM",
                "2026-07-10", role=role, job_id=legacy,
                snippet="Support: 18001234567")
            _ev(store, 3, "IBM application status", "rejection", "IBM",
                "2026-07-16", role=role, job_id=canonical)

            reconcile.recompute(store)

            active = [app for app in store.applications() if app["company"] == "IBM"]
            assert [(app["job_id"], app["status"]) for app in active] == [
                (canonical, "rejected"),
            ]
            assert {event["job_id"] for event in store.mail_events()} == {canonical}
            hidden = store.get_application(legacy, include_tombstoned=True)
            assert hidden["tombstone_reason"] == "orphan_mail_application"
        finally:
            store.close()


def test_recompute_keeps_conflicting_requisitions_separate():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        try:
            role = "Security Analyst"
            legacy = "mail:legacy-ibm"
            scraped = Job(
                source="ats", title=role, company="IBM",
                url="https://ibm.example/jobs/222222",
            ).ensure_id()
            store.upsert_job(scraped)
            canonical = scraped.id
            _ev(store, 1, f"IBM application submitted - 111111 - {role}",
                "confirmation", "IBM", "2026-07-08", role=role, job_id=legacy)
            _ev(store, 2, f"IBM application submitted - 222222 - {role}",
                "confirmation", "IBM", "2026-07-09", role=role, job_id=canonical)

            reconcile.recompute(store)

            assert {event["job_id"] for event in store.mail_events()} == {
                legacy, canonical,
            }
        finally:
            store.close()


def test_recompute_does_not_merge_duplicate_with_user_notes():
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        try:
            role = "Security Consultant-SOC(XSIAM)"
            legacy = "mail:legacy-note"
            canonical = inbox._link_job("IBM", role, {})
            store.set_application(Application(
                job_id=legacy, status="interview", company="IBM", title=role,
                source="inbox", notes="[2026-07-17] user-confirmed submission",
            ))
            _ev(store, 1, f"IBM assessment - 124835 - {role}", "assessment", "IBM",
                "2026-07-10", role=role, job_id=legacy)
            _ev(store, 2, f"IBM application status - 124835 - {role}", "rejection",
                "IBM", "2026-07-16", role=role, job_id=canonical)

            reconcile.recompute(store)

            assert {event["job_id"] for event in store.mail_events()} == {
                legacy, canonical,
            }
            assert store.get_application(legacy)["notes"] == (
                "[2026-07-17] user-confirmed submission"
            )
        finally:
            store.close()


def test_reclassify_reparses_stale_company():
    # A company an older rule mangled ("IBM Acquisition") heals to the re-parsed
    # sender name, and the rebuilt app carries the corrected "IBM".
    with tempfile.TemporaryDirectory() as tmp:
        _, store = _store(tmp)
        ev = MailEvent(
            account="me@x.com", uid="9",
            subject="Action Required:IBM Assessments for completion - 124835 Security Consultant",
            signal="assessment", company="IBM Acquisition", role="", date="2026-07-10",
            job_id="mail:ibm", from_name="IBM Talent Acquisition", from_domain="ibm.com",
            snippet="Dear Mohit. Complete IBM's recorded competency assessment.").ensure_id()
        store.upsert_mail_event(ev)
        reconcile.reclassify(store)
        assert store.get_application("mail:ibm")["company"] == "IBM"
        store.close()
