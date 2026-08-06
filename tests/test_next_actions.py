"""Next actions: the work that can change an outcome today (issue #103)."""
import datetime as dt
import os
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

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


# --- due dates -----------------------------------------------------------------


def _zoned_cfg(zone: str, days: int = 7) -> dict:
    return {"apply": {"followup_days": days, "campaign": {"timezone": zone}}}


def _applied_at(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _due_for(cfg: dict, applied: dt.datetime) -> dt.date:
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:dated", status="applied", company="Acme",
                title="Analyst", applied_at=_applied_at(applied),
            ))
            return actions.next_actions(cfg, store)[0].due_at


def test_the_due_date_is_the_day_the_follow_up_window_closed():
    due = _due_for(_zoned_cfg("UTC"), dt.datetime(2026, 1, 5, 9, 0))

    assert due == dt.date(2026, 1, 12)


def test_the_due_date_is_read_in_the_configured_zone_not_utc():
    """20:00 UTC is already tomorrow in Kolkata, and the chase belongs on the day the
    user will actually see it."""
    due = _due_for(_zoned_cfg("Asia/Kolkata"), dt.datetime(2026, 1, 5, 20, 0))

    assert due == dt.date(2026, 1, 13)
    assert _due_for(_zoned_cfg("UTC"), dt.datetime(2026, 1, 5, 20, 0)) == dt.date(2026, 1, 12)


def _has_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return False
    return True


@pytest.mark.skipif(not _has_zone("America/New_York"),
                    reason="host ships no tzdata for a daylight-saving zone")
def test_the_due_date_survives_a_daylight_saving_change():
    """The window opens in EST and closes in EDT. Converting the instant picks up the
    new offset; carrying the old one would file this a day early."""
    due = _due_for(_zoned_cfg("America/New_York"), dt.datetime(2026, 3, 4, 4, 30))

    assert due == dt.date(2026, 3, 11)


def test_an_unparseable_applied_date_is_left_out_rather_than_guessed():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.set_application(Application(
                job_id="mail:undated", status="applied", company="Acme",
                title="Analyst", applied_at="not a date",
            ))

            assert actions.next_actions(_cfg(), store) == []


def test_a_timezone_jobscope_cannot_resolve_still_lists_the_queue():
    """Campaigns refuse to send at an unknown local time, and should. This only reads,
    so a config typo must not take the whole chase list down with it."""
    due = _due_for(_zoned_cfg("Mars/Olympus"), dt.datetime(2026, 1, 5, 9, 0))

    assert due == dt.date(2026, 1, 12)


# --- calendar export -----------------------------------------------------------


def _action(**over) -> actions.NextAction:
    base = {
        "job_id": "mail:quiet", "reason": "follow_up", "company": "Acme Security",
        "title": "Security Analyst", "age_days": 12, "due_at": dt.date(2026, 3, 11),
    }
    return actions.NextAction(**{**base, **over})


STAMP = dt.datetime(2026, 3, 12, 8, 0, tzinfo=dt.UTC)


def _uid_line(text: str) -> str:
    return next(line for line in text.split("\r\n") if line.startswith("UID:"))


def test_an_empty_queue_still_writes_a_valid_calendar():
    text = actions.to_ics([], now=STAMP)

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.endswith("END:VCALENDAR\r\n")
    assert "BEGIN:VEVENT" not in text


def test_a_dated_action_becomes_one_all_day_event():
    text = actions.to_ics([_action()], now=STAMP)
    lines = text.split("\r\n")

    assert "DTSTART;VALUE=DATE:20260311" in lines
    # DTEND is exclusive, so a one-day event ends on the 12th
    assert "DTEND;VALUE=DATE:20260312" in lines
    assert "DTSTAMP:20260312T080000Z" in lines
    assert "SUMMARY:Follow up: Acme Security" in lines
    assert any(line.startswith("UID:") and line.endswith("@jobscope.local") for line in lines)


def test_the_exported_date_round_trips_back_to_the_due_date():
    action = _action()
    text = actions.to_ics([action], now=STAMP)

    stamped = next(line for line in text.split("\r\n") if line.startswith("DTSTART"))
    assert dt.datetime.strptime(stamped.split(":")[1], "%Y%m%d").date() == action.due_at


def test_re_exporting_updates_the_same_entry_instead_of_adding_a_copy():
    """Calendars dedupe on UID, so a stable UID is what stops a weekly export from
    stacking six copies of the same chase."""
    first = actions.to_ics([_action()], now=STAMP)
    later = actions.to_ics([_action(age_days=19)], now=STAMP + dt.timedelta(days=7))

    assert _uid_line(first) == _uid_line(later)


def test_a_different_action_on_the_same_job_gets_its_own_entry():
    follow_up = actions.to_ics([_action()], now=STAMP)
    ghosted = actions.to_ics([_action(reason="ghosted")], now=STAMP)

    assert _uid_line(follow_up) != _uid_line(ghosted)


def test_punctuation_in_a_company_name_cannot_break_the_format():
    text = actions.to_ics([_action(company="Acme, Inc; Security")], now=STAMP)

    assert "SUMMARY:Follow up: Acme\\, Inc\\; Security" in text.split("\r\n")


def test_a_long_line_is_folded_on_octet_width():
    text = actions.to_ics([_action(title="Principal " + "Very Senior " * 12)], now=STAMP)
    lines = text.split("\r\n")

    assert all(len(line.encode()) <= 75 for line in lines)
    # a folded continuation is marked by the single leading space
    assert any(line.startswith(" ") for line in lines)
