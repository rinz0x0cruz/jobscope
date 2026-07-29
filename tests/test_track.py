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
        assert "Follow-up due (3," in out
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
