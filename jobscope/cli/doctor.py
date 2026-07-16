"""Offline operational readiness checks for Jobscope."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from jobscope.core.config import inbox_password
from jobscope.core.snapshot import SnapshotValidationError, validate_sqlite_snapshot
from jobscope.core.store import Store


@dataclass(frozen=True, slots=True)
class Check:
    level: str
    name: str
    detail: str


def inspect(cfg: dict, *, secret_lookup: Callable[[dict, dict], str] = inbox_password,
            which: Callable[[str], str | None] = shutil.which,
            publish_ready: Callable[[], bool] | None = None) -> list[Check]:
    checks: list[Check] = []
    db_path = Path((cfg.get("output", {}) or {}).get("db_path") or "data/jobscope.db")
    if not db_path.is_file():
        checks.append(Check("error", "database", f"missing: {db_path}"))
    else:
        try:
            validate_sqlite_snapshot(db_path)
        except SnapshotValidationError as exc:
            checks.append(Check("error", "database", str(exc)))
        else:
            checks.append(Check("ok", "database", f"valid Jobscope SQLite: {db_path}"))

    inbox_cfg = cfg.get("inbox", {}) or {}
    accounts = inbox_cfg.get("accounts") or []
    if inbox_cfg.get("enabled") and not accounts:
        checks.append(Check("error", "inbox", "enabled but no accounts are configured"))
    for index, account in enumerate(accounts, start=1):
        email = (account or {}).get("email", "")
        env_name = (account or {}).get("password_env", "")
        label = email or f"account {index}"
        if not email or not env_name:
            checks.append(Check(
                "error", "inbox", f"{label}: email and password_env are required"))
        elif inbox_cfg.get("enabled") and not secret_lookup(cfg, account):
            checks.append(Check(
                "error", "inbox", f"{label}: secret {env_name} is unavailable"))
        else:
            checks.append(Check("ok", "inbox", f"{label}: secret reference is ready"))

    for executable in ("git", "node", "npm"):
        available = bool(which(executable) or which(f"{executable}.cmd"))
        checks.append(Check(
            "ok" if available else "warn", "toolchain",
            f"{executable}: {'available' if available else 'not found'}",
        ))

    if publish_ready is None:
        from jobscope.deliver.serve import apps_passphrase_available
        publish_ready = apps_passphrase_available
    publish_passphrase = publish_ready()
    publish_required = bool((cfg.get("serve", {}) or {}).get("refresh_enabled", True))
    checks.append(Check(
        "ok" if publish_passphrase else ("error" if publish_required else "warn"), "publish",
        "JOBSCOPE_APPS_PASSPHRASE is available"
        if publish_passphrase else "publish passphrase not found in the environment",
    ))

    if db_path.is_file() and not any(
            check.level == "error" and check.name == "database" for check in checks):
        with Store(str(db_path)) as store:
            health = store.source_health()
            monitors = store.list_company_monitors()
            last_failure = store.meta_get("refresh:last_failure", "") or ""
            failed_stage = store.meta_get("refresh:last_failed_stage", "") or ""
        unhealthy = [row for row in health if row["status"] not in {
            "ok", "empty", "recovered",
        }]
        if unhealthy:
            summary = ", ".join(
                f"{row['source']}={row['status']}" for row in unhealthy[:8])
            checks.append(Check("warn", "sources", summary))
        elif health:
            checks.append(Check("ok", "sources", f"{len(health)} source record(s) healthy"))
        else:
            checks.append(Check("warn", "sources", "no source-health records yet"))
        unresolved = [
            monitor for monitor in monitors
            if monitor["status"] == "active" and monitor["resolution_status"] != "resolved"
        ]
        active = [monitor for monitor in monitors if monitor["status"] == "active"]
        if unresolved:
            names = ", ".join(monitor["company"] for monitor in unresolved[:8])
            checks.append(Check("warn", "companies", f"needs portal setup: {names}"))
        elif active:
            checks.append(Check("ok", "companies", f"{len(active)} active monitor(s) resolved"))
        else:
            checks.append(Check("warn", "companies", "no active company monitors; run `companies seed`"))
        if last_failure:
            checks.append(Check(
                "warn", "refresh", f"last failure {last_failure} at {failed_stage or 'unknown'}"))
        else:
            checks.append(Check("ok", "refresh", "no recorded refresh failure"))
    return checks


def run(cfg: dict) -> int:
    checks = inspect(cfg)
    for check in checks:
        print(f"  [{check.level.upper():5}] {check.name}: {check.detail}")
    errors = sum(check.level == "error" for check in checks)
    warnings = sum(check.level == "warn" for check in checks)
    print(f"\n  doctor: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0