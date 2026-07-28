"""Scheduled-slot identity, single claim, coalescing, and heartbeat.

Platform cron is assumed at-least-once, out of order, and late.
"""
import json
import threading

import pytest

from jobscope.core.store import Store
from jobscope.deliver import automation

_HOUR_MS = 60 * 60 * 1000
_SCHEDULED = 1_800_000_000_000


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AUTOMATION_DISABLED", raising=False)
    monkeypatch.setenv("JOBSCOPE_ARTIFACT_ID", "artifact-under-test")
    with Store(str(tmp_path / "automation.db")) as handle:
        yield handle


def test_slot_identity_is_stable_and_version_scoped():
    first = automation.slot_id("refresh", _SCHEDULED)

    assert first == automation.slot_id("refresh", _SCHEDULED)
    assert first != automation.slot_id("tick", _SCHEDULED)
    assert first != automation.slot_id("refresh", _SCHEDULED + 1000)
    assert len(first) == 24


@pytest.mark.parametrize("operation,scheduled", [
    ("publish", _SCHEDULED),
    ("refresh", 0),
    ("refresh", -1),
    ("refresh", "not-a-number"),
    ("refresh", None),
])
def test_unknown_operations_and_times_are_rejected(store, operation, scheduled):
    outcome, record = automation.claim(
        store, operation=operation, scheduled_ms=scheduled, now_ms=_SCHEDULED,
    )

    assert outcome == "invalid"
    assert record == {}
    assert store.meta_get(automation.SLOT_KEY, "") == ""


def test_first_claim_wins_and_the_retry_returns_the_same_result(store):
    outcome, record = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    assert outcome == "claimed"
    assert record["state"] == "running"
    assert record["artifact"] == "artifact-under-test"

    # A retried transport delivers the identical scheduled instant.
    repeat, shared = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED + 5_000,
    )
    assert repeat == "duplicate"
    assert shared["slot"] == record["slot"]

    automation.finish(store, record["slot"], state="ok", code="done", run_id="abc123")

    terminal, finished = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED + 9_000,
    )
    assert terminal == "duplicate"
    assert finished["state"] == "ok"
    assert finished["run_id"] == "abc123"


def test_simultaneous_claims_execute_once(tmp_path):
    path = str(tmp_path / "race.db")
    Store(path).close()
    start = threading.Barrier(6)
    outcomes = []
    lock = threading.Lock()

    def attempt():
        with Store(path) as handle:
            start.wait()
            outcome, _ = automation.claim(
                handle, operation="tick", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
            )
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert outcomes.count("claimed") == 1
    assert set(outcomes) <= {"claimed", "duplicate"}


def test_a_different_slot_is_deferred_while_work_is_running(store):
    automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    next_slot = _SCHEDULED + 5 * 60_000

    outcome, record = automation.claim(
        store, operation="refresh", scheduled_ms=next_slot, now_ms=next_slot,
    )

    assert outcome == "busy"
    assert record["scheduled_ms"] == _SCHEDULED


def test_an_abandoned_claim_is_taken_over_after_the_grace_period(store):
    automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    later = _SCHEDULED + automation.ABANDONED_CLAIM_MS + 1_000

    outcome, record = automation.claim(
        store, operation="refresh", scheduled_ms=later, now_ms=later,
    )

    assert outcome == "claimed"
    assert record["scheduled_ms"] == later


def test_an_older_slot_cannot_supersede_a_newer_one(store):
    _, first = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    automation.finish(store, first["slot"], state="ok")

    outcome, record = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED - _HOUR_MS,
        now_ms=_SCHEDULED + 1_000,
    )

    assert outcome == "superseded"
    assert record["scheduled_ms"] == _SCHEDULED


def test_a_slot_delivered_far_too_late_is_dropped(store):
    outcome, record = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED,
        now_ms=_SCHEDULED + automation.MAX_LATENESS_MS + 1,
    )

    assert outcome == "stale"
    assert record["lateness_ms"] > automation.MAX_LATENESS_MS
    assert store.meta_get(automation.SLOT_KEY, "") == ""


def test_missed_slots_coalesce_into_one_counted_execution(store):
    _, first = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED,
        period_ms=_HOUR_MS, now_ms=_SCHEDULED,
    )
    automation.finish(store, first["slot"], state="ok")
    resumed = _SCHEDULED + 4 * _HOUR_MS

    outcome, record = automation.claim(
        store, operation="refresh", scheduled_ms=resumed,
        period_ms=_HOUR_MS, now_ms=resumed,
    )

    assert outcome == "claimed"
    assert record["missed"] == 3
    assert record["lateness_ms"] == 0
    # One record exists, so the skipped slots cannot fan out into extra work.
    assert json.loads(store.meta_get(automation.SLOT_KEY))["slot"] == record["slot"]


def test_lateness_is_recorded_without_blocking_a_recoverable_slot(store):
    late = _SCHEDULED + 60_000

    _, record = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED, now_ms=late,
    )

    assert record["lateness_ms"] == 60_000


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_the_environment_kill_switch_blocks_new_mutation(store, monkeypatch, value):
    monkeypatch.setenv("JOBSCOPE_AUTOMATION_DISABLED", value)

    outcome, _ = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )

    assert outcome == "disabled"
    assert store.meta_get(automation.SLOT_KEY, "") == ""


def test_the_stored_kill_switch_blocks_new_mutation_immediately(store):
    store.meta_set(automation.DISABLED_KEY, "1")

    outcome, _ = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    assert outcome == "disabled"
    assert automation.status(store)["disabled"] is True

    store.meta_set(automation.DISABLED_KEY, "0")
    outcome, _ = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    assert outcome == "claimed"


def test_finishing_a_foreign_or_missing_slot_changes_nothing(store):
    _, record = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    before = store.meta_get(automation.SLOT_KEY)

    assert automation.finish(store, "not-the-slot", state="ok") == {}
    assert automation.finish(store, "", state="ok") == {}
    assert store.meta_get(automation.SLOT_KEY) == before
    assert store.meta_get(automation.HEARTBEAT_KEY, "") == ""

    automation.finish(store, record["slot"], state="ok")
    assert json.loads(store.meta_get(automation.HEARTBEAT_KEY))["state"] == "ok"


def test_an_unknown_terminal_state_is_recorded_as_an_error(store):
    _, record = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )

    finished = automation.finish(store, record["slot"], state="whatever")

    assert finished["state"] == "error"


def test_the_backend_run_id_links_to_the_slot_once(store):
    _, record = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )

    automation.link_run(store, record["slot"], "run-one")
    automation.link_run(store, record["slot"], "run-two")
    automation.link_run(store, "other-slot", "run-three")

    assert json.loads(store.meta_get(automation.SLOT_KEY))["run_id"] == "run-one"


def test_a_missing_or_aged_heartbeat_reads_as_stale(store):
    assert automation.status(store)["stale"] is True

    _, record = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED,
        period_ms=_HOUR_MS, now_ms=_SCHEDULED,
    )
    automation.finish(store, record["slot"], state="ok", code="done", run_id="r1")
    fresh = automation.status(store)

    assert fresh["stale"] is False
    assert fresh["state"] == "ok"
    assert fresh["operation"] == "refresh"
    assert fresh["run_id"] == "r1"
    assert fresh["running"] is False

    aged = json.loads(store.meta_get(automation.HEARTBEAT_KEY))
    stale_now = int(aged["finished_ms"]) + 2 * _HOUR_MS + 1
    assert automation.status(store, now_ms=stale_now)["stale"] is True


def test_corrupt_slot_metadata_does_not_wedge_the_schedule(store):
    store.meta_set(automation.SLOT_KEY, "{not json")

    outcome, record = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )

    assert outcome == "claimed"
    assert json.loads(store.meta_get(automation.SLOT_KEY))["slot"] == record["slot"]


def test_a_slot_scheduled_in_the_future_cannot_wedge_the_schedule(store):
    ahead = _SCHEDULED + 365 * 24 * _HOUR_MS

    outcome, _ = automation.claim(
        store, operation="refresh", scheduled_ms=ahead, now_ms=_SCHEDULED,
    )

    assert outcome == "invalid"
    assert store.meta_get(automation.SLOT_KEY, "") == ""

    # The real slot that follows must still be claimable.
    accepted, _ = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    assert accepted == "claimed"


def test_small_clock_skew_is_tolerated(store):
    outcome, record = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED + 30_000, now_ms=_SCHEDULED,
    )

    assert outcome == "claimed"
    assert record["lateness_ms"] == 0


@pytest.mark.parametrize("scheduled", [10 ** 30, -(10 ** 30), 2 ** 63])
def test_an_unrepresentable_scheduled_time_is_refused_not_crashed(store, scheduled):
    outcome, _ = automation.claim(
        store, operation="tick", scheduled_ms=scheduled, now_ms=_SCHEDULED,
    )

    assert outcome == "invalid"
    assert store.meta_get(automation.SLOT_KEY, "") == ""


@pytest.mark.parametrize("corrupt", [
    {"slot": "other", "state": "running", "accepted_ms": "not-a-number"},
    {"slot": "other", "state": "running", "accepted_ms": None, "scheduled_ms": "soon"},
    {"slot": "other", "state": [], "scheduled_ms": {}},
    {"slot": None, "state": "ok", "scheduled_ms": 1.5},
])
def test_corrupt_slot_fields_never_raise(store, corrupt):
    store.meta_set(automation.SLOT_KEY, json.dumps(corrupt))

    outcome, _ = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )

    assert outcome in {"claimed", "busy", "duplicate", "superseded"}


def test_a_corrupt_heartbeat_reads_as_stale_instead_of_raising(store):
    store.meta_set(automation.HEARTBEAT_KEY, json.dumps({
        "state": "ok", "finished_ms": "whenever", "period_ms": None,
        "duration_ms": [], "missed": "many", "lateness_ms": {},
    }))

    report = automation.status(store)

    assert report["stale"] is True
    assert report["duration_ms"] == 0
    assert report["missed"] == 0


def test_finishing_a_claim_with_a_corrupt_timestamp_never_raises(store):
    _, record = automation.claim(
        store, operation="tick", scheduled_ms=_SCHEDULED, now_ms=_SCHEDULED,
    )
    broken = dict(record, accepted_ms="not-a-number")
    store.meta_set(automation.SLOT_KEY, json.dumps(broken, sort_keys=True))

    finished = automation.finish(store, record["slot"], state="ok")

    assert finished["state"] == "ok"
    assert finished["duration_ms"] >= 0


def test_a_period_of_zero_or_nonsense_never_invents_missed_slots(store):
    _, first = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED,
        period_ms=-5, now_ms=_SCHEDULED,
    )
    automation.finish(store, first["slot"], state="ok")

    _, second = automation.claim(
        store, operation="refresh", scheduled_ms=_SCHEDULED + _HOUR_MS,
        period_ms=0, now_ms=_SCHEDULED + _HOUR_MS,
    )

    assert first["missed"] == 0
    assert second["missed"] == 0
