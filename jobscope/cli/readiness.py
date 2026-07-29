"""One fail-closed activation-readiness report for the optional lanes.

Reads existing evidence only: `doctor`, campaign sending readiness, source
health, refresh markers, and recorded canary results. It never activates, sends,
scans, publishes, restores, or mutates a mailbox. Live checks happen only under
an explicit ``--canary`` request, and even then use non-mutating operations.

Output carries lane state, blocker codes, evidence age, and hashes only: never a
secret, address, message body, resume text, or prompt.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path

LANES = ("storage", "discovery", "inbox", "smtp", "outreach", "scheduler", "ai")
DEPENDS: dict[str, tuple[str, ...]] = {
    "storage": (),
    "discovery": ("storage",),
    "inbox": ("storage",),
    "smtp": ("storage",),
    # AI is never a dependency of a deterministic lane.
    "outreach": ("storage", "inbox", "smtp"),
    "scheduler": ("storage", "outreach"),
    "ai": (),
}
CANARY_LANES = ("inbox", "smtp")
READY_STATES = frozenset({"preflight_passed", "canary_passed", "active"})
_EVIDENCE_MAX_AGE_DAYS = 30.0
_TICK_MAX_AGE_DAYS = 2.0
_CANARY_KEY = "readiness:canary:"
# Only reviewed automatic providers describe the current discovery lane. Rows
# from a retired source survive in `source_health` forever, so counting them
# would make a dead lane look live and permanently unhealthy. The live scanner
# is `monitor.scan_monitor`, recording `monitor:<id>`; the `ats:<company>` batch
# fetch that once wrote the other prefix was deleted, so matching it measured a
# prefix nothing writes -- discovery could never show a runtime success, and
# `source_unhealthy` could never fire however many boards failed.
_DISCOVERY_SOURCE_PREFIX = "monitor:"
_DISCOVERY_HEALTHY = {"ok", "empty", "partial"}      # benign ats.BoardStatus
_INBOX_HEALTHY = {"ok", "empty", "recovered"}


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _parse(value: str) -> _dt.datetime | None:
    try:
        parsed = _dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


def _age_days(value: str) -> float | None:
    parsed = _parse(value)
    if parsed is None:
        return None
    return round(max(0.0, (_now() - parsed).total_seconds() / 86400), 3)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def artifact_id() -> str:
    return os.environ.get("JOBSCOPE_ARTIFACT_ID", "").strip() or "local"


def _hosted(cfg: dict) -> bool:
    return bool(
        (cfg.get("_runtime", {}) or {}).get("hosted")
        or os.environ.get("JOBSCOPE_HOSTED", "").strip().lower() in {"1", "true", "yes"}
    )


def config_hash(cfg: dict, lane: str) -> str:
    """Hash a non-secret, non-PII projection of the lane's effective config."""
    ai = cfg.get("ai", {}) or {}
    inbox = cfg.get("inbox", {}) or {}
    email = cfg.get("email", {}) or {}
    outreach = (cfg.get("apply", {}) or {}).get("outreach", {}) or {}
    accounts = inbox.get("accounts") or []
    projections: dict[str, object] = {
        "storage": {"db": bool((cfg.get("output", {}) or {}).get("db_path"))},
        "discovery": {"companies": len((cfg.get("search", {}) or {}).get("companies") or [])},
        "inbox": {
            "host": inbox.get("imap_host"), "port": inbox.get("imap_port"),
            "folder": inbox.get("folder"), "sent_folder": inbox.get("sent_folder"),
            "spam": bool(inbox.get("include_spam")), "accounts": len(accounts),
            "secrets": sorted(
                str(item.get("password_env") or "")
                for item in accounts if isinstance(item, dict)
            ),
        },
        "smtp": {
            "host": email.get("smtp_host"), "port": email.get("smtp_port"),
            "secret": email.get("password_env"),
            "sender": _digest(str(email.get("from_addr") or "")),
        },
        "outreach": {
            "enabled": bool(outreach.get("enabled")),
            "campaign": outreach.get("campaign") or {},
            "cooldown_days": outreach.get("cooldown_days"),
        },
        "scheduler": {"campaign": outreach.get("campaign") or {}},
        "ai": {
            "provider": ai.get("provider"), "base_url": ai.get("base_url"),
            "model": ai.get("model"), "local_models": ai.get("local_models"),
            "local_purposes": ai.get("local_purposes"),
            "remote": bool((ai.get("remote") or {}).get("enabled")),
            "budget": ai.get("budget") or {},
            "quorum": bool((cfg.get("quorum", {}) or {}).get("enabled")),
        },
    }
    return _digest(projections.get(lane, {}))


def record_canary(store, lane: str, cfg: dict, *, result: str) -> dict:
    """Persist the one canary fact that cannot be recomputed later."""
    if lane not in CANARY_LANES:
        raise ValueError(f"unknown canary lane: {lane}")
    evidence = {
        "at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": result,
        "config_hash": config_hash(cfg, lane),
        "artifact": artifact_id(),
    }
    store.meta_set(_CANARY_KEY + lane, json.dumps(evidence, sort_keys=True))
    return evidence


def _canary_evidence(store, cfg: dict, lane: str) -> tuple[dict, list[str]]:
    if lane not in CANARY_LANES:
        return {}, []
    raw = store.meta_get(_CANARY_KEY + lane, "") or ""
    if not raw:
        return {}, ["canary_missing"]
    try:
        evidence = json.loads(raw)
    except (TypeError, ValueError):
        return {}, ["canary_invalid"]
    if not isinstance(evidence, dict):
        return {}, ["canary_invalid"]
    blockers: list[str] = []
    age = _age_days(str(evidence.get("at") or ""))
    if evidence.get("result") != "passed":
        blockers.append("canary_failed")
    if age is None:
        blockers.append("canary_invalid")
    elif age > _EVIDENCE_MAX_AGE_DAYS:
        blockers.append("canary_stale")
    if evidence.get("config_hash") != config_hash(cfg, lane):
        blockers.append("canary_config_drift")
    if evidence.get("artifact") != artifact_id():
        blockers.append("canary_artifact_drift")
    return {"at": str(evidence.get("at") or ""), "age_days": age,
            "result": str(evidence.get("result") or "")}, blockers


def _storage_lane(cfg: dict, store) -> tuple[bool, list[str], str]:
    from jobscope.core.snapshot import SnapshotValidationError, validate_sqlite_snapshot
    from jobscope.core.sqlite_runtime import require_safe_sqlite

    blockers: list[str] = []
    if _hosted(cfg):
        # The pinned runtime identity gates hosted mutation only; a local
        # deterministic install stays fully usable on the stock interpreter.
        try:
            require_safe_sqlite(verify_identity=True)
        except RuntimeError:
            blockers.append("sqlite_unsafe")
    db_path = Path((cfg.get("output", {}) or {}).get("db_path") or "data/jobscope.db")
    if not db_path.is_file():
        blockers.append("database_missing")
    else:
        try:
            validate_sqlite_snapshot(db_path)
        except SnapshotValidationError:
            blockers.append("database_invalid")
    return True, blockers, store.meta_get("refresh:last_date", "") or ""


def _discovery_lane(cfg: dict, store) -> tuple[bool, list[str], str]:
    monitors = store.list_company_monitors()
    active = [item for item in monitors if item["status"] == "active"]
    resolved = [item for item in active if item["resolution_status"] == "resolved"]
    companies = (cfg.get("search", {}) or {}).get("companies") or []
    health = [row for row in store.source_health()
              if str(row["source"]).startswith(_DISCOVERY_SOURCE_PREFIX)]
    blockers: list[str] = []
    if active and not resolved:
        blockers.append("no_resolved_monitors")
    if any(row["status"] not in _DISCOVERY_HEALTHY for row in health):
        blockers.append("source_unhealthy")
    last = max((str(row["checked_at"] or "") for row in health), default="")
    return bool(active or companies), blockers, last


def _inbox_lane(cfg: dict, store) -> tuple[bool, list[str], str]:
    from jobscope.core.config import inbox_password

    inbox_cfg = cfg.get("inbox", {}) or {}
    accounts = inbox_cfg.get("accounts") or []
    blockers: list[str] = []
    if not accounts:
        blockers.append("no_accounts")
    for account in accounts:
        # A hand-edited config can hold anything, and readiness is the command an
        # operator runs to find that out, so it reports instead of crashing.
        if not isinstance(account, dict) or not account.get("email") \
                or not account.get("password_env"):
            blockers.append("account_incomplete")
        elif not inbox_password(cfg, account):
            blockers.append("secret_unavailable")
    health = [row for row in store.source_health() if str(row["source"]).startswith("inbox:")]
    if any(row["status"] not in _INBOX_HEALTHY for row in health):
        blockers.append("sync_unhealthy")
    last = max((str(row["checked_at"] or "") for row in health), default="")
    return bool(inbox_cfg.get("enabled")), sorted(set(blockers)), last


def _smtp_lane(cfg: dict, store) -> tuple[bool, list[str], str]:
    from jobscope.core.config import smtp_password

    email_cfg = cfg.get("email", {}) or {}
    blockers: list[str] = []
    if not all(email_cfg.get(field) for field in ("from_addr", "smtp_host", "smtp_port")):
        blockers.append("config_incomplete")
    if not smtp_password(cfg):
        blockers.append("secret_unavailable")
    return bool(email_cfg.get("enabled")), blockers, store.last_outreach_campaign_sent_at() or ""


def _outreach_lane(cfg: dict, store) -> tuple[bool, list[str], str, bool]:
    from jobscope.apply.campaigns import sending_readiness

    outreach_cfg = (cfg.get("apply", {}) or {}).get("outreach", {}) or {}
    blockers: list[str] = []
    delivery_blocker = store.outreach_campaign_delivery_blocker()
    if delivery_blocker:
        blockers.append(delivery_blocker)
    if outreach_cfg.get("enabled") and not sending_readiness(cfg, store)["ok"]:
        blockers.append("sending_readiness_failed")
    return (
        bool(outreach_cfg.get("enabled")), blockers,
        store.last_outreach_campaign_sent_at() or "", bool(delivery_blocker),
    )


def _scheduler_lane(store) -> tuple[bool, list[str], str]:
    from jobscope.deliver import automation

    last = store.meta_get("campaign:replies:last_checked_at", "") or ""
    status = store.meta_get("campaign:replies:last_status", "") or ""
    heartbeat = automation.status(store)
    blockers: list[str] = []
    if not last:
        blockers.append("never_ticked")
    else:
        age = _age_days(last)
        if age is not None and age > _TICK_MAX_AGE_DAYS:
            blockers.append("tick_stale")
    if status and status not in {"ok", "not_needed", "not_fetched"}:
        blockers.append("reply_sync_unhealthy")
    # Only judge the scheduled clock once it has actually produced a slot.
    if heartbeat["state"]:
        if heartbeat["stale"]:
            blockers.append("heartbeat_stale")
        if heartbeat["state"] == "error":
            blockers.append("last_slot_failed")
    if heartbeat["disabled"]:
        blockers.append("automation_disabled")
    return bool(last or heartbeat["state"]), blockers, max(last, heartbeat["finished"])


def _ai_lane(cfg: dict) -> tuple[bool, list[str], str]:
    from jobscope.core import ai as _ai

    ai_cfg = cfg.get("ai", {}) or {}
    purposes = ai_cfg.get("local_purposes") or []
    routed = [name for name in purposes if _ai.available(cfg, name)]
    blockers = [] if routed else ["no_valid_route"]
    return bool(ai_cfg.get("enabled")), blockers, ""


def _state(enabled: bool, blockers: list[str], last_success: str,
           lane: str, paused: bool) -> str:
    if not enabled:
        return "disabled"
    if paused:
        return "paused"
    if blockers:
        return "configured"
    if lane in CANARY_LANES:
        return "active" if last_success else "canary_passed"
    return "active" if last_success else "preflight_passed"


def report(cfg: dict, store) -> dict:
    """Return the full lane report; performs no network or mutation."""
    lanes: dict[str, dict] = {}
    paused_lanes: set[str] = set()

    computed: dict[str, tuple[bool, list[str], str]] = {
        "storage": _storage_lane(cfg, store),
        "discovery": _discovery_lane(cfg, store),
        "inbox": _inbox_lane(cfg, store),
        "smtp": _smtp_lane(cfg, store),
        "scheduler": _scheduler_lane(store),
        "ai": _ai_lane(cfg),
    }
    enabled, blockers, last_success, paused = _outreach_lane(cfg, store)
    computed["outreach"] = (enabled, blockers, last_success)
    if paused:
        paused_lanes.add("outreach")

    for lane in LANES:
        enabled, blockers, last_success = computed[lane]
        evidence, canary_blockers = _canary_evidence(store, cfg, lane)
        if not enabled:
            # A lane nobody asked for is healthy, not broken. `--require` still
            # fails on it because `disabled` is not an activatable state.
            blockers = []
        else:
            blockers = blockers + canary_blockers
            for dependency in DEPENDS[lane]:
                state = lanes[dependency]["state"]
                if state == "disabled":
                    blockers.append(f"dependency_disabled:{dependency}")
                elif state not in READY_STATES:
                    blockers.append(f"dependency_blocked:{dependency}")
        lanes[lane] = {
            "lane": lane,
            "state": _state(enabled, blockers, last_success,
                            lane, lane in paused_lanes),
            "enabled": enabled,
            "blockers": sorted(set(blockers)),
            "depends_on": list(DEPENDS[lane]),
            "config_hash": config_hash(cfg, lane),
            "canary": evidence,
            "last_success_age_days": _age_days(last_success),
        }
    return {"artifact": artifact_id(), "lanes": [lanes[lane] for lane in LANES]}


def _blocked(result: dict, lane: str) -> list[str]:
    by_lane = {item["lane"]: item for item in result["lanes"]}
    pending, seen, problems = [lane], set(), []
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(DEPENDS[current])
        item = by_lane[current]
        if item["blockers"]:
            problems.extend(f"{current}: {code}" for code in item["blockers"])
        elif item["state"] not in READY_STATES:
            problems.append(f"{current}: {item['state']}")
    return sorted(problems)


def _next_action(item: dict) -> str:
    if item["state"] == "disabled":
        if item["lane"] == "discovery":
            # Discovery has no enable flag; it needs targets.
            return "add company monitors or search.companies entries"
        return "enable in config when you intend to activate"
    if item["blockers"]:
        return f"resolve {item['blockers'][0]}"
    if item["lane"] in CANARY_LANES and not item["canary"]:
        return f"run `readiness --canary {item['lane']}`"
    return "ready; activation remains a manual decision"


def run(cfg: dict, store, *, require: str = "", canary: str = "",
        account: str = "", as_json: bool = False) -> int:
    if canary:
        if canary not in CANARY_LANES:
            print(f"  unknown canary lane: {canary}")
            return 2
        passed = _run_canary(cfg, store, canary, account)
        if passed == "usage":
            return 2
        if passed == "failed":
            return 1

    result = report(cfg, store)
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for item in result["lanes"]:
            age = item["last_success_age_days"]
            detail = ", ".join(item["blockers"]) or _next_action(item)
            print(f"  [{item['state'].upper():<16}] {item['lane']:<10} "
                  f"{'last success ' + str(age) + 'd' if age is not None else 'no runtime success'}"
                  f"  {detail}")
        print(f"\n  readiness: artifact {result['artifact']}")

    if require:
        if require not in LANES:
            print(f"  unknown lane: {require}")
            return 2
        problems = _blocked(result, require)
        if problems:
            if not as_json:
                for problem in problems:
                    print(f"  blocked {problem}")
            return 1
    return 0


def _run_canary(cfg: dict, store, lane: str, account: str) -> str:
    """Run the one explicit live check for a lane; never sends or mutates mail.

    Returns ``passed``, ``failed``, or ``usage``. A usage error is an operator
    mistake rather than a fact about the lane, so it is never recorded.
    """
    if lane == "inbox":
        from . import inbox_canary
        try:
            passed = inbox_canary.run(cfg, account) == 0
        except ValueError as exc:
            print(f"  {exc}")
            return "usage"
        except RuntimeError as exc:
            print(f"  inbox canary failed: {exc}")
            passed = False
    else:
        from jobscope.deliver import email
        outcome = email.preflight(cfg)
        passed = bool(outcome.get("ok"))
        print(f"  smtp preflight: {outcome.get('code') or 'unknown'}")
    record_canary(store, lane, cfg, result="passed" if passed else "failed")
    return "passed" if passed else "failed"
