"""Deterministic scheduled-slot identity, single claim, and heartbeat.

The edge Worker supplies only an operation name and its UTC scheduled time. The
backend re-derives the slot identity, claims it atomically in SQLite, and refuses
every duplicate, superseded, overlapping, or stale slot. Platform cron is treated
as at-least-once and possibly late, never as exactly-once.

No network call is issued while a transaction is held: a claim is one short
compare-and-set, the work runs outside it, and completion is one more write.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os

# Bumping the version invalidates every previously claimed slot, so a redeployed
# operation cannot be silently deduplicated against the old one's history.
OPERATION_VERSION = "1"
OPERATIONS = ("refresh", "tick")
SLOT_KEY = "automation:slot"
HEARTBEAT_KEY = "automation:heartbeat"
DISABLED_KEY = "automation:disabled"

# A slot delivered this late is a backlog artifact, not a schedule: drop it and
# wait for the next one rather than replaying stale work.
MAX_LATENESS_MS = 30 * 60 * 1000
# A slot dated beyond this in the future comes from a broken clock or a forged
# header. Accepting one would make every real slot look superseded forever.
MAX_SKEW_MS = 5 * 60 * 1000
# A claim whose process died leaves a running record behind; after this it may be
# taken over so one lost response cannot wedge the schedule forever.
ABANDONED_CLAIM_MS = 30 * 60 * 1000
TERMINAL_STATES = frozenset({"ok", "error", "skipped"})


def _as_int(value: object, default: int = 0) -> int:
    """Read one persisted number without trusting its type."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _now_ms() -> int:
    return int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)


def _iso(milliseconds: int) -> str:
    moment = _dt.datetime.fromtimestamp(milliseconds / 1000, _dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def slot_id(operation: str, scheduled_ms: int) -> str:
    """Stable identity for one scheduled instant of one operation version."""
    payload = f"{OPERATION_VERSION}:{operation}:{int(scheduled_ms)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def disabled(store) -> bool:
    """Kill switch: environment for deploys, metadata for an immediate stop."""
    if os.environ.get("JOBSCOPE_AUTOMATION_DISABLED", "").strip().lower() in {
        "1", "true", "yes",
    }:
        return True
    return (store.meta_get(DISABLED_KEY, "") or "").strip() == "1"


def _load(store, key: str) -> tuple[str, dict]:
    raw = store.meta_get(key, "") or ""
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        value = {}
    return raw, value if isinstance(value, dict) else {}


def claim(store, *, operation: str, scheduled_ms: object, period_ms: int = 0,
          now_ms: int | None = None) -> tuple[str, dict]:
    """Claim one slot exactly once.

    Returns an outcome and the governing record: `claimed`, `duplicate`, `busy`,
    `superseded`, `stale`, `disabled`, or `invalid`.
    """
    if operation not in OPERATIONS:
        return "invalid", {}
    try:
        scheduled = int(scheduled_ms)
        period = max(0, int(period_ms))
    except (TypeError, ValueError):
        return "invalid", {}
    if scheduled <= 0:
        return "invalid", {}

    now = _now_ms() if now_ms is None else int(now_ms)
    # Cloudflare delivers at or after the scheduled instant, so a materially
    # future slot is never legitimate.
    if scheduled - now > MAX_SKEW_MS:
        return "invalid", {}
    if disabled(store):
        return "disabled", {}

    slot = slot_id(operation, scheduled)
    lateness = max(0, now - scheduled)
    raw, current = _load(store, SLOT_KEY)

    # A retried transport delivers the same slot: return the one shared result.
    if current.get("slot") == slot:
        return "duplicate", current
    # An out-of-order delivery is refused as superseded before it is judged late,
    # because the newer slot already represents the latest intended state.
    previous = _as_int(current.get("scheduled_ms"))
    if previous > scheduled:
        return "superseded", current
    if lateness > MAX_LATENESS_MS:
        return "stale", {"slot": slot, "lateness_ms": lateness}
    if current and _as_text(current.get("state")) not in TERMINAL_STATES:
        if now - _as_int(current.get("accepted_ms")) < ABANDONED_CLAIM_MS:
            return "busy", current

    # Missed slots coalesce into this one execution and are only counted.
    missed = 0
    if period > 0 and previous:
        missed = max(0, round((scheduled - previous) / period) - 1)
    record = {
        "slot": slot, "operation": operation, "version": OPERATION_VERSION,
        "scheduled": _iso(scheduled), "scheduled_ms": scheduled,
        "accepted": _iso(now), "accepted_ms": now,
        "finished": "", "finished_ms": 0, "duration_ms": 0,
        "state": "running", "code": "", "run_id": "",
        "missed": missed, "lateness_ms": lateness, "period_ms": period,
        "artifact": os.environ.get("JOBSCOPE_ARTIFACT_ID", "").strip() or "local",
    }
    if not store.meta_compare_and_set(
        SLOT_KEY, raw or None, json.dumps(record, sort_keys=True),
    ):
        # Another request claimed first; report against the winning record.
        _, winner = _load(store, SLOT_KEY)
        return ("duplicate" if winner.get("slot") == slot else "busy"), winner
    return "claimed", record


def finish(store, slot: str, *, state: str, code: str = "",
           run_id: str = "") -> dict:
    """Record one terminal result and publish it as the heartbeat."""
    raw, current = _load(store, SLOT_KEY)
    if not slot or current.get("slot") != slot:
        return {}
    now = _now_ms()
    record = dict(current)
    record.update(
        state=state if state in TERMINAL_STATES else "error",
        code=str(code or "")[:80], run_id=str(run_id or "")[:64],
        finished=_iso(now), finished_ms=now,
        duration_ms=max(0, now - _as_int(current.get("accepted_ms"), now)),
    )
    payload = json.dumps(record, sort_keys=True)
    if store.meta_compare_and_set(SLOT_KEY, raw, payload):
        # A lagging heartbeat reads as stale, which is the safe direction.
        store.meta_set(HEARTBEAT_KEY, payload)
    return record


def link_run(store, slot: str, run_id: str) -> None:
    """Attach the backend execution ID to an in-progress claim."""
    raw, current = _load(store, SLOT_KEY)
    if not slot or current.get("slot") != slot or current.get("run_id"):
        return
    record = dict(current, run_id=str(run_id or "")[:64])
    store.meta_compare_and_set(SLOT_KEY, raw, json.dumps(record, sort_keys=True))


def status(store, *, now_ms: int | None = None) -> dict:
    """Latest terminal heartbeat for an independent read-only observer."""
    _, heartbeat = _load(store, HEARTBEAT_KEY)
    _, current = _load(store, SLOT_KEY)
    now = _now_ms() if now_ms is None else int(now_ms)
    finished_ms = _as_int(heartbeat.get("finished_ms"))
    age_ms = max(0, now - finished_ms) if finished_ms > 0 else None
    period = _as_int(heartbeat.get("period_ms"))
    return {
        "state": _as_text(heartbeat.get("state")),
        "operation": _as_text(heartbeat.get("operation")),
        "slot": _as_text(heartbeat.get("slot")),
        "scheduled": _as_text(heartbeat.get("scheduled")),
        "finished": _as_text(heartbeat.get("finished")),
        "code": _as_text(heartbeat.get("code")),
        "run_id": _as_text(heartbeat.get("run_id")),
        "duration_ms": _as_int(heartbeat.get("duration_ms")),
        "lateness_ms": _as_int(heartbeat.get("lateness_ms")),
        "missed": _as_int(heartbeat.get("missed")),
        "artifact": _as_text(heartbeat.get("artifact")),
        "age_ms": age_ms,
        "running": _as_text(current.get("state")) == "running",
        "disabled": disabled(store),
        "stale": age_ms is None or (period > 0 and age_ms > period * 2),
    }
