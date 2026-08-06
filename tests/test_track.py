"""Tests for the application funnel view (`jobscope track`)."""
import os
import tempfile

from jobscope.apply import track
from jobscope.core.model import Application, Job
from jobscope.core.store import Store


def _applied(store, company: str, applied_at: str) -> None:
    job = Job(
        source="inbox", title="Security Engineer", company=company,
        url=f"https://x/{company}",
    ).ensure_id()
    store.upsert_job(job)
    store.set_application(Application(
        job_id=job.id, status="applied", company=company, applied_at=applied_at,
    ))


def test_follow_up_reminders_survive_applications_of_equal_age(capsys):
    """Applications submitted on the same day used to crash the whole command.

    The reminder list sorted bare ``(age, application)`` tuples, so a tie on age
    fell through to comparing the application dicts and raised TypeError. The
    funnel printed first, so `track` looked like it worked right up to the point
    it died -- and with dozens of applications a tie is a certainty.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "t.db"))
        for company in ("Initech", "Acme", "Globex"):
            _applied(store, company, "2000-01-01T00:00:00Z")

        assert track.run(store, cfg={"apply": {"followup_days": 7}}) == 0

        out = capsys.readouterr().out
        assert "Likely ghosted (3," in out
        # Same age, so the company name breaks the tie deterministically.
        assert out.index("Acme /") < out.index("Globex /") < out.index("Initech /")
        store.close()


def test_reminders_list_the_longest_silent_application_first(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(os.path.join(tmp, "t.db"))
        _applied(store, "Recent", "2020-01-01T00:00:00Z")
        _applied(store, "Ancient", "2000-01-01T00:00:00Z")

        assert track.run(store, cfg={"apply": {"followup_days": 7}}) == 0

        out = capsys.readouterr().out
        assert out.index("Ancient /") < out.index("Recent /")
        store.close()


def _prepare(store, job_id="ref:1", status="applied", **over):
    store.set_application(Application(
        job_id=job_id, status=status, company="Acme Security", title="Analyst",
        applied_at="2026-08-01T09:00:00Z", notes="phone screen booked", **over))


def test_a_referral_can_be_recorded_by_hand():
    """Before this the only writer was a regex over inbound mail, so a referral made
    for you in person could never be recorded."""
    with tempfile.TemporaryDirectory() as tmp:
        with Store(os.path.join(tmp, "t.db")) as store:
            _prepare(store)

            assert track.run(store, referred_by="ref:1=Priya Nair") == 0
            assert store.get_application("ref:1")["referred_by"] == "Priya Nair"


def test_recording_a_referral_does_not_erase_the_application():
    """status, applied_at and notes are overwritten by the upsert rather than
    coalesced, so a naive write would quietly reset the funnel."""
    with tempfile.TemporaryDirectory() as tmp:
        with Store(os.path.join(tmp, "t.db")) as store:
            _prepare(store, status="interview")

            track.run(store, referred_by="ref:1=Priya Nair")

            app = store.get_application("ref:1")
            assert app["status"] == "interview"
            assert app["applied_at"] == "2026-08-01T09:00:00Z"
            assert app["notes"] == "phone screen booked"
            assert app["company"] == "Acme Security"


def test_a_referral_can_be_corrected():
    with tempfile.TemporaryDirectory() as tmp:
        with Store(os.path.join(tmp, "t.db")) as store:
            _prepare(store)
            track.run(store, referred_by="ref:1=Priya Nir")

            assert track.run(store, referred_by="ref:1=Priya Nair") == 0
            assert store.get_application("ref:1")["referred_by"] == "Priya Nair"


def test_an_empty_name_is_refused_rather_than_silently_ignored(capsys):
    """The column coalesces empties, so accepting one would look like it worked
    while leaving the previous referrer in place."""
    with tempfile.TemporaryDirectory() as tmp:
        with Store(os.path.join(tmp, "t.db")) as store:
            _prepare(store)
            track.run(store, referred_by="ref:1=Priya Nair")

            assert track.run(store, referred_by="ref:1=   ") == 1
            assert store.get_application("ref:1")["referred_by"] == "Priya Nair"
            assert "referrer name is required" in capsys.readouterr().out


def test_a_referral_for_an_unknown_application_is_refused(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        with Store(os.path.join(tmp, "t.db")) as store:
            assert track.run(store, referred_by="nope=Priya Nair") == 1
            assert "no application for nope" in capsys.readouterr().out


def test_a_malformed_expression_is_refused(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        with Store(os.path.join(tmp, "t.db")) as store:
            assert track.run(store, referred_by="just-a-name") == 1
            assert "--referred-by job_id=name" in capsys.readouterr().out
