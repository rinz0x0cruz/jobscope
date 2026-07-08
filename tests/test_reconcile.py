"""Tests for funnel reconciliation (`ingest.reconcile`): instance-splitting +
conservative reclassify. Deterministic, offline."""
import os
import tempfile

from jobscope.core.config import load_config
from jobscope.core.model import MailEvent
from jobscope.core.store import Store
from jobscope.ingest import reconcile


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
        store.close()
