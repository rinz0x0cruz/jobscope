"""Next actions: the work that can change an outcome today (issue #103)."""
import datetime as dt
import os
import tempfile

from jobscope.apply import actions
from jobscope.core.model import Application, MailEvent
from jobscope.core.store import Store


def _cfg(days: int = 7) -> dict:
    return {"apply": {"followup_days": days}}


def _days_ago(days: int) -> str:
    return (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _store(tmp: str) -> Store:
    return Store(os.path.join(tmp, "actions.db"))


def test_a_silent_application_past_the_window_needs_a_follow_up():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:quiet", status="applied", company="Acme Security",
                title="Security Analyst", applied_at=_days_ago(12),
            ))

            due = actions.next_actions(_cfg(), store)

            assert [item.job_id for item in due] == ["mail:quiet"]
            assert due[0].reason == "follow_up"
            assert due[0].company == "Acme Security"


def test_an_application_that_already_moved_is_not_chased():
    """Silence is the trigger, not age: an interviewing application needs no nudge."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:moving", status="interview", company="Northwind",
                title="Detection Engineer", applied_at=_days_ago(30),
            ))

            assert actions.next_actions(_cfg(), store) == []


def test_the_longest_silence_is_listed_first():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            for job_id, days in (("mail:recent", 9), ("mail:oldest", 40), ("mail:middle", 20)):
                store.set_application(Application(
                    job_id=job_id, status="applied", company=job_id,
                    applied_at=_days_ago(days),
                ))

            listed = [item.job_id for item in actions.next_actions(_cfg(), store)]

            assert listed == ["mail:oldest", "mail:middle", "mail:recent"]


def test_an_application_inside_the_window_is_left_alone():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:fresh", status="applied", company="Contoso",
                applied_at=_days_ago(3),
            ))

            assert actions.next_actions(_cfg(), store) == []


def test_a_long_silence_reads_as_ghosted_rather_than_a_nudge():
    """The frontend draws this line at 21 days (`pipeline.ts` GHOST_DAYS) and the two
    halves of the product must not disagree about what ghosted means."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:silent", status="applied", company="Initech",
                applied_at=_days_ago(40),
            ))

            assert [item.reason for item in actions.next_actions(_cfg(), store)] == ["ghosted"]


def test_an_application_that_got_a_real_reply_is_not_chased():
    """Status sits at `applied` even after a recruiter writes back, so status alone is
    not silence. Mirrors RESPONSE_SIGNALS in `pipeline.ts`."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:replied", status="applied", company="Umbrella",
                applied_at=_days_ago(30),
            ))
            store.upsert_mail_event(MailEvent(
                account="me", uid="1", job_id="mail:replied", signal="recruiter",
                date=_days_ago(2),
            ).ensure_id())

            assert actions.next_actions(_cfg(), store) == []
