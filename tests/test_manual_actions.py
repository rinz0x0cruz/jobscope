"""Manual next actions: the steps that cannot be derived (issue #103)."""
import datetime as dt
import os
import tempfile

import pytest

from jobscope.apply import actions
from jobscope.core.store import Store

TODAY = dt.date(2026, 8, 6)


def _store(tmp: str) -> Store:
    return Store(os.path.join(tmp, "manual.db"))


def test_a_manual_action_starts_open():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            row = store.add_manual_action(
                "Send the take-home", due_at="2026-08-10", company="Acme")

            assert row["state"] == "open"
            assert row["label"] == "Send the take-home"
            assert row["due_at"] == "2026-08-10"
            assert row["created_at"]


def test_recording_the_same_step_twice_does_not_stack_duplicates():
    """The same label, job and date is the same intent. A queue that grows a copy every
    time you re-run the command is a queue you stop trusting."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            first = store.add_manual_action("Chase referral", due_at="2026-08-10",
                                            job_id="mail:a")
            again = store.add_manual_action("chase referral", due_at="2026-08-10",
                                            job_id="mail:a", note="via Priya")

            assert first["id"] == again["id"]
            assert len(store.manual_actions()) == 1
            assert store.manual_action(first["id"])["note"] == "via Priya"


def test_a_step_with_no_label_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            with pytest.raises(ValueError):
                store.add_manual_action("   ")


def test_completing_is_reversible():
    """Marking the wrong row done has to be undoable: nothing here asserts an
    application status or an email outcome, so reopening invents nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            action_id = store.add_manual_action("Reply to recruiter")["id"]

            assert store.set_manual_action_state(action_id, "completed") is True
            assert store.manual_action(action_id)["state"] == "completed"
            assert store.manual_action(action_id)["updated_at"]

            assert store.set_manual_action_state(action_id, "open") is True
            assert store.manual_action(action_id)["state"] == "open"


def test_cancelling_is_recorded_separately_from_completing():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            action_id = store.add_manual_action("Ask about relocation")["id"]
            store.set_manual_action_state(action_id, "cancelled")

            assert store.manual_action(action_id)["state"] == "cancelled"
            assert store.manual_actions(state="cancelled")[0]["id"] == action_id
            assert store.manual_actions(state="completed") == []


def test_an_unknown_state_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            action_id = store.add_manual_action("Something")["id"]

            with pytest.raises(ValueError):
                store.set_manual_action_state(action_id, "done-ish")


def test_moving_an_action_that_does_not_exist_reports_it():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            assert store.set_manual_action_state("act:missing", "completed") is False


def test_the_soonest_due_comes_first_and_undated_work_sorts_last():
    with tempfile.TemporaryDirectory() as tmp:
        with _store(tmp) as store:
            store.add_manual_action("later", due_at="2026-09-01")
            store.add_manual_action("someday")
            store.add_manual_action("sooner", due_at="2026-08-07")

            assert [row["label"] for row in store.manual_actions()] == [
                "sooner", "later", "someday"]


# --- views ---------------------------------------------------------------------


def _row(**over) -> dict:
    return {"state": "open", "due_at": "", **over}


def test_work_due_today_or_overdue_belongs_to_today():
    assert actions.bucket_of(_row(due_at="2026-08-06"), TODAY) == actions.TODAY
    assert actions.bucket_of(_row(due_at="2026-07-01"), TODAY) == actions.TODAY


def test_work_due_later_is_upcoming():
    assert actions.bucket_of(_row(due_at="2026-08-07"), TODAY) == actions.UPCOMING


def test_undated_work_stays_visible_in_today():
    """A queue that hides undated work is how work gets lost."""
    assert actions.bucket_of(_row(), TODAY) == actions.TODAY


def test_an_unreadable_due_date_does_not_hide_the_action():
    assert actions.bucket_of(_row(due_at="next tuesday"), TODAY) == actions.TODAY


def test_finished_work_leaves_the_active_views():
    assert actions.bucket_of(_row(state="completed", due_at="2026-07-01"), TODAY) == actions.DONE
    assert actions.bucket_of(_row(state="cancelled"), TODAY) == actions.CANCELLED
