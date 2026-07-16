"""Persistent company monitors, job provenance, and review decisions."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .base import now_iso

MONITOR_STATUSES = frozenset({"active", "paused", "removed"})
RESOLUTION_STATUSES = frozenset({"resolved", "unresolved", "unsupported"})
REVIEW_STATES = frozenset({"pending", "saved", "dismissed"})
REVIEW_ORIGINS = frozenset({"monitored", "discovery", "legacy"})

_COMPANY_SUFFIXES = frozenset({
    "ag", "co", "company", "corp", "corporation", "gmbh", "inc", "incorporated",
    "limited", "llc", "ltd", "plc", "private", "pvt", "solutions", "systems",
    "technologies", "technology",
})


def normalize_company_key(company: str) -> str:
    """Return a stable, human-auditable key for company-name matching."""
    normalized = unicodedata.normalize("NFKC", company or "").casefold()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def monitor_source_key(monitor_id: str) -> str:
    return f"monitor:{monitor_id}"


def _monitor_id(company_key: str) -> str:
    digest = hashlib.sha256(company_key.encode("utf-8")).hexdigest()[:16]
    return f"company:{digest}"


def _json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


def _merge_values(*groups: Iterable[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for raw in group:
            value = str(raw).strip()
            if value and value not in merged:
                merged.append(value)
    return merged


def _validate_choice(value: str, allowed: frozenset[str], label: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in allowed:
        raise ValueError(f"invalid {label}: {value!r}")
    return normalized


class MonitoringMixin:
    """SQLite operations for the company-first review workflow."""

    def _monitor_row(self, monitor_id: str) -> Any:
        return self.conn.execute(
            "SELECT * FROM company_monitors WHERE id = ?", (monitor_id,),
        ).fetchone()

    @staticmethod
    def _monitor_dict(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["origins"] = _json_list(result.pop("origins_json", "[]"))
        return result

    def _merge_monitors(self, target_id: str, source_id: str) -> None:
        if target_id == source_id:
            return
        target = self._monitor_row(target_id)
        source = self._monitor_row(source_id)
        if target is None or source is None:
            return
        origins = _merge_values(
            _json_list(target["origins_json"]), _json_list(source["origins_json"]),
        )
        for link in self.conn.execute(
            "SELECT job_id, first_seen, last_seen FROM company_monitor_jobs "
            "WHERE monitor_id = ?", (source_id,),
        ).fetchall():
            existing = self.conn.execute(
                "SELECT first_seen, last_seen FROM company_monitor_jobs "
                "WHERE monitor_id = ? AND job_id = ?", (target_id, link["job_id"]),
            ).fetchone()
            first_seen = min(existing["first_seen"], link["first_seen"]) if existing else link["first_seen"]
            last_seen = max(existing["last_seen"], link["last_seen"]) if existing else link["last_seen"]
            self.conn.execute(
                "INSERT INTO company_monitor_jobs (monitor_id, job_id, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(monitor_id, job_id) DO UPDATE SET "
                "first_seen = excluded.first_seen, last_seen = excluded.last_seen",
                (target_id, link["job_id"], first_seen, last_seen),
            )
        self.conn.execute("DELETE FROM company_monitor_jobs WHERE monitor_id = ?", (source_id,))
        self.conn.execute("DELETE FROM company_monitors WHERE id = ?", (source_id,))
        self.conn.execute(
            "UPDATE company_monitors SET origins_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(origins), now_iso(), target_id),
        )

    def _upsert_company_monitor(
        self,
        company: str,
        *,
        provider: str = "",
        slug: str = "",
        careers_url: str = "",
        status: str = "active",
        resolution_status: str | None = None,
        added_from: str = "user",
    ) -> dict[str, Any]:
        display = (company or "").strip()
        company_key = normalize_company_key(display)
        if not company_key:
            raise ValueError("company is required")
        provider = (provider or "").strip().lower()
        slug = (slug or "").strip()
        if bool(provider) != bool(slug):
            raise ValueError("provider and slug must be supplied together")
        status = _validate_choice(status, MONITOR_STATUSES, "monitor status")
        resolution = resolution_status or ("resolved" if provider and slug else "unresolved")
        resolution = _validate_choice(resolution, RESOLUTION_STATUSES, "resolution status")
        origin = (added_from or "user").strip().lower()

        key_row = self.conn.execute(
            "SELECT * FROM company_monitors WHERE company_key = ?", (company_key,),
        ).fetchone()
        board_row = None
        if provider and slug:
            board_row = self.conn.execute(
                "SELECT * FROM company_monitors WHERE provider = ? AND slug = ?",
                (provider, slug),
            ).fetchone()
        if key_row is not None and board_row is not None and key_row["id"] != board_row["id"]:
            self._merge_monitors(board_row["id"], key_row["id"])
            key_row = None
            board_row = self._monitor_row(board_row["id"])
        existing = board_row or key_row
        timestamp = now_iso()
        if existing is None:
            monitor_id = _monitor_id(company_key)
            self.conn.execute(
                "INSERT INTO company_monitors "
                "(id, company_key, company, provider, slug, careers_url, status, "
                "resolution_status, origins_json, created_at, updated_at, last_success_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')",
                (monitor_id, company_key, display, provider, slug, careers_url.strip(), status,
                 resolution, json.dumps([origin] if origin else []), timestamp, timestamp),
            )
        else:
            monitor_id = existing["id"]
            origins = _merge_values(_json_list(existing["origins_json"]), [origin])
            self.conn.execute(
                "UPDATE company_monitors SET "
                "company = ?, provider = ?, slug = ?, careers_url = ?, status = ?, "
                "resolution_status = ?, origins_json = ?, updated_at = ? WHERE id = ?",
                (existing["company"] or display,
                 provider or existing["provider"], slug or existing["slug"],
                 careers_url.strip() or existing["careers_url"], status, resolution,
                 json.dumps(origins), timestamp, monitor_id),
            )
        return self._monitor_dict(self._monitor_row(monitor_id))

    def upsert_company_monitor(self, company: str, **kwargs: Any) -> dict[str, Any]:
        with self.conn:
            return self._upsert_company_monitor(company, **kwargs)

    def get_company_monitor(self, monitor_id_or_company: str) -> dict[str, Any] | None:
        value = (monitor_id_or_company or "").strip()
        row = self._monitor_row(value)
        if row is None:
            row = self.conn.execute(
                "SELECT * FROM company_monitors WHERE company_key = ?",
                (normalize_company_key(value),),
            ).fetchone()
        return self._monitor_dict(row) if row is not None else None

    def list_company_monitors(
        self, *, status: str | None = None, include_removed: bool = False,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            normalized = _validate_choice(status, MONITOR_STATUSES, "monitor status")
            where = " WHERE status = ?"
            params.append(normalized)
        elif not include_removed:
            where = " WHERE status <> 'removed'"
        rows = self.conn.execute(
            "SELECT * FROM company_monitors" + where + " ORDER BY company COLLATE NOCASE",
            params,
        ).fetchall()
        return [self._monitor_dict(row) for row in rows]

    def _set_company_monitor_status(self, monitor_id: str, status: str) -> dict[str, Any]:
        normalized = _validate_choice(status, MONITOR_STATUSES, "monitor status")
        cursor = self.conn.execute(
            "UPDATE company_monitors SET status = ?, updated_at = ? WHERE id = ?",
            (normalized, now_iso(), monitor_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"unknown monitor: {monitor_id}")
        return self._monitor_dict(self._monitor_row(monitor_id))

    def set_company_monitor_status(self, monitor_id: str, status: str) -> dict[str, Any]:
        with self.conn:
            return self._set_company_monitor_status(monitor_id, status)

    def mark_monitor_success(self, monitor_id: str, checked_at: str | None = None) -> None:
        timestamp = checked_at or now_iso()
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE company_monitors SET last_success_at = ?, updated_at = ? WHERE id = ?",
                (timestamp, timestamp, monitor_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown monitor: {monitor_id}")

    def _link_monitor_job(self, monitor_id: str, job_id: str, seen_at: str | None = None) -> None:
        if self._monitor_row(monitor_id) is None:
            raise ValueError(f"unknown monitor: {monitor_id}")
        if not (job_id or "").strip():
            raise ValueError("job_id is required")
        timestamp = seen_at or now_iso()
        self.conn.execute(
            "INSERT INTO company_monitor_jobs (monitor_id, job_id, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(monitor_id, job_id) DO UPDATE SET "
            "last_seen = excluded.last_seen",
            (monitor_id, job_id, timestamp, timestamp),
        )

    def link_monitor_job(self, monitor_id: str, job_id: str, seen_at: str | None = None) -> None:
        with self.conn:
            self._link_monitor_job(monitor_id, job_id, seen_at)

    def monitor_job_ids(self, monitor_id: str) -> list[str]:
        return [row["job_id"] for row in self.conn.execute(
            "SELECT job_id FROM company_monitor_jobs WHERE monitor_id = ? ORDER BY first_seen",
            (monitor_id,),
        )]

    def monitored_job_ids(self) -> set[str]:
        return {
            row["job_id"] for row in self.conn.execute(
                "SELECT DISTINCT job_id FROM company_monitor_jobs"
            )
        }

    def reconcile_monitor_jobs(self, monitor_id: str, live_job_ids: Iterable[str]) -> int:
        live = {job_id for job_id in live_job_ids if job_id}
        if not live:
            return 0
        timestamp = now_iso()
        with self.conn:
            for job_id in live:
                self._link_monitor_job(monitor_id, job_id, timestamp)
            linked = self.monitor_job_ids(monitor_id)
            gone = [job_id for job_id in linked if job_id not in live]
            if gone:
                self.conn.executemany(
                    "UPDATE jobs SET status = 'closed', closed_at = ? "
                    "WHERE id = ? AND COALESCE(status, 'open') = 'open'",
                    [(timestamp, job_id) for job_id in gone],
                )
            return len(gone)

    def _set_job_review(
        self, job_id: str, state: str, origins: Iterable[str] = (),
    ) -> dict[str, Any]:
        job_id = (job_id or "").strip()
        if not job_id:
            raise ValueError("job_id is required")
        normalized = _validate_choice(state, REVIEW_STATES, "review state")
        clean_origins = [
            _validate_choice(origin, REVIEW_ORIGINS, "review origin") for origin in origins
        ]
        existing = self.conn.execute(
            "SELECT * FROM job_reviews WHERE job_id = ?", (job_id,),
        ).fetchone()
        timestamp = now_iso()
        merged_origins = _merge_values(
            _json_list(existing["origins_json"]) if existing else [], clean_origins,
        )
        first_seen = existing["first_seen"] if existing else timestamp
        reviewed_at = ""
        if normalized in {"saved", "dismissed"}:
            reviewed_at = (
                existing["reviewed_at"]
                if existing and existing["state"] == normalized and existing["reviewed_at"]
                else timestamp
            )
        self.conn.execute(
            "INSERT INTO job_reviews (job_id, state, origins_json, first_seen, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(job_id) DO UPDATE SET "
            "state = excluded.state, origins_json = excluded.origins_json, "
            "reviewed_at = excluded.reviewed_at",
            (job_id, normalized, json.dumps(merged_origins), first_seen, reviewed_at),
        )
        return self.get_job_review(job_id) or {}

    def set_job_review(
        self, job_id: str, state: str, *, origins: Iterable[str] = (),
    ) -> dict[str, Any]:
        with self.conn:
            return self._set_job_review(job_id, state, origins)

    def ensure_job_review(
        self, job_id: str, *, origins: Iterable[str], default_state: str = "pending",
    ) -> dict[str, Any]:
        existing = self.get_job_review(job_id)
        state = existing["state"] if existing else default_state
        with self.conn:
            return self._set_job_review(job_id, state, origins)

    @staticmethod
    def _review_dict(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["origins"] = _json_list(result.pop("origins_json", "[]"))
        monitor_ids = result.pop("monitor_ids", "") or ""
        result["monitor_ids"] = [value for value in monitor_ids.split(",") if value]
        return result

    def get_job_review(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT r.*, GROUP_CONCAT(mj.monitor_id) AS monitor_ids "
            "FROM job_reviews r LEFT JOIN company_monitor_jobs mj ON mj.job_id = r.job_id "
            "WHERE r.job_id = ? GROUP BY r.job_id", (job_id,),
        ).fetchone()
        return self._review_dict(row) if row is not None else None

    def list_job_reviews(self, *, state: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if state:
            where = " WHERE r.state = ?"
            params.append(_validate_choice(state, REVIEW_STATES, "review state"))
        rows = self.conn.execute(
            "SELECT r.*, GROUP_CONCAT(mj.monitor_id) AS monitor_ids "
            "FROM job_reviews r LEFT JOIN company_monitor_jobs mj ON mj.job_id = r.job_id" +
            where + " GROUP BY r.job_id ORDER BY r.first_seen DESC",
            params,
        ).fetchall()
        return [self._review_dict(row) for row in rows]

    def company_monitor_summaries(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT m.*, h.status AS health_status, h.detail AS health_detail, "
            "h.item_count AS board_count, h.checked_at, "
            "COUNT(DISTINCT CASE WHEN COALESCE(j.status, 'open') = 'open' "
            "  AND COALESCE(j.tier, 'Skip') <> 'Skip' THEN j.id END) AS open_matches, "
            "COUNT(DISTINCT CASE WHEN r.state = 'pending' THEN r.job_id END) AS pending_count, "
            "COUNT(DISTINCT CASE WHEN r.state = 'saved' THEN r.job_id END) AS saved_count "
            "FROM company_monitors m "
            "LEFT JOIN source_health h ON h.source = 'monitor:' || m.id "
            "LEFT JOIN company_monitor_jobs mj ON mj.monitor_id = m.id "
            "LEFT JOIN jobs j ON j.id = mj.job_id "
            "LEFT JOIN job_reviews r ON r.job_id = mj.job_id "
            "WHERE m.status <> 'removed' GROUP BY m.id ORDER BY m.company COLLATE NOCASE"
        ).fetchall()
        return [self._monitor_dict(row) for row in rows]

    def apply_monitoring_actions(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(actions, list) or len(actions) > 100:
            raise ValueError("actions must be a list of at most 100 items")
        results: list[dict[str, Any]] = []
        with self.conn:
            for action in actions:
                if not isinstance(action, dict):
                    raise ValueError("each action must be an object")
                action_type = action.get("type")
                if action_type == "monitor.status":
                    results.append(self._set_company_monitor_status(
                        str(action.get("monitor_id") or ""), str(action.get("status") or ""),
                    ))
                elif action_type == "review.set":
                    results.append(self._set_job_review(
                        str(action.get("job_id") or ""), str(action.get("state") or ""),
                        action.get("origins") or (),
                    ))
                else:
                    raise ValueError(f"unsupported monitoring action: {action_type!r}")
        return results