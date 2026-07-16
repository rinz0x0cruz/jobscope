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


def _audit_checks(store) -> list[Check]:
    checks: list[Check] = []
    running = store.conn.execute(
        "SELECT id FROM reconciliation_runs WHERE status = 'running' "
        "ORDER BY started_at LIMIT 5"
    ).fetchall()
    if running:
        checks.append(Check(
            "warn", "audit",
            "running reconciliation run(s): " + ", ".join(row["id"] for row in running),
        ))

    orphan_decisions = store.conn.execute(
        "SELECT COUNT(*) AS count FROM reconciliation_decisions d "
        "LEFT JOIN reconciliation_runs r ON r.id = d.run_id WHERE r.id IS NULL"
    ).fetchone()["count"]
    if orphan_decisions:
        checks.append(Check(
            "warn", "audit", f"{orphan_decisions} decision(s) reference a missing run",
        ))

    malformed = store.conn.execute(
        "SELECT job_id FROM applications WHERE COALESCE(tombstoned_at, '') <> '' "
        "AND (COALESCE(tombstone_reason, '') = '' "
        "OR COALESCE(reconciliation_run_id, '') = '') LIMIT 5"
    ).fetchall()
    if malformed:
        checks.append(Check(
            "warn", "audit",
            "tombstone missing reason/run: " + ", ".join(row["job_id"] for row in malformed),
        ))

    exempt_tombstones = store.conn.execute(
        "SELECT job_id FROM applications WHERE COALESCE(tombstoned_at, '') <> '' "
        "AND reconciliation_exempt = 1 LIMIT 5"
    ).fetchall()
    if exempt_tombstones:
        checks.append(Check(
            "warn", "audit",
            "tombstoned application remains recovery-exempt: " +
            ", ".join(row["job_id"] for row in exempt_tombstones),
        ))

    duplicate_active = store.conn.execute(
        "SELECT job_id FROM applications WHERE COALESCE(tombstoned_at, '') = '' "
        "GROUP BY job_id HAVING COUNT(*) > 1 LIMIT 5"
    ).fetchall()
    if duplicate_active:
        checks.append(Check(
            "warn", "audit",
            "duplicate active application IDs: " +
            ", ".join(row["job_id"] for row in duplicate_active),
        ))

    missing_links = store.conn.execute(
        "SELECT e.id FROM mail_events e LEFT JOIN applications a ON a.job_id = e.job_id "
        "WHERE COALESCE(e.job_id, '') <> '' AND a.job_id IS NULL "
        "AND e.signal IN ('confirmation', 'recruiter', 'assessment', 'interview', "
        "'offer', 'rejection') LIMIT 5"
    ).fetchall()
    if missing_links:
        checks.append(Check(
            "warn", "audit",
            "mail event(s) link to missing applications: " +
            ", ".join(row["id"] for row in missing_links),
        ))

    latest = store.conn.execute(
        "SELECT applications_before, applications_after FROM reconciliation_runs "
        "WHERE status = 'completed' AND baseline_only = 0 "
        "AND applications_after IS NOT NULL ORDER BY completed_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    if latest:
        before = int(latest["applications_before"] or 0)
        after = int(latest["applications_after"] or 0)
        dropped = before - after
        if before and dropped >= 5 and dropped / before > 0.25:
            checks.append(Check(
                "warn", "audit",
                f"latest reconciliation count dropped {before} -> {after} ({dropped} rows)",
            ))

    if not checks:
        run_count = store.conn.execute(
            "SELECT COUNT(*) AS count FROM reconciliation_runs"
        ).fetchone()["count"]
        checks.append(Check("ok", "audit", f"{run_count} reconciliation run(s); integrity clean"))
    return checks


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
            audit_checks = _audit_checks(store)
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
        checks.extend(audit_checks)
    return checks


def run(cfg: dict) -> int:
    checks = inspect(cfg)
    for check in checks:
        print(f"  [{check.level.upper():5}] {check.name}: {check.detail}")
    errors = sum(check.level == "error" for check in checks)
    warnings = sum(check.level == "warn" for check in checks)
    print(f"\n  doctor: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0