"""Validated company-monitor and review actions shared by CLI, serve, and CI."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any
from urllib.parse import urlparse

from jobscope.analyze.review import score_jobs
from jobscope.ingest import ats, monitor

MAX_ACTIONS = 100
MAX_ACTION_BYTES = 20_000

_ALLOWED_FIELDS = {
    "monitor.upsert": {"type", "company", "provider", "slug", "careers_url", "status", "job_id"},
    "monitor.status": {"type", "monitor_id", "status"},
    "monitor.scan": {"type", "monitor_id"},
    "monitor.contacts": {"type", "monitor_id"},
    "review.set": {"type", "job_id", "state"},
    "application.restore": {"type", "job_id"},
    "application.note": {"type", "job_id", "text", "when"},
}


def _clean_string(value: Any, label: str, *, limit: int = 500, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    cleaned = value.strip()
    if required and not cleaned:
        raise ValueError(f"{label} is required")
    if len(cleaned) > limit:
        raise ValueError(f"{label} is too long")
    return cleaned


def _clean_url(value: Any) -> str:
    url = _clean_string(value, "careers_url", limit=1000)
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValueError("careers_url is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("careers_url must be an http(s) URL")
    return url


def _prepare_actions(cfg: dict, store, actions: Any) -> list[dict[str, Any]]:
    if not isinstance(actions, list) or not actions or len(actions) > MAX_ACTIONS:
        raise ValueError(f"actions must contain 1 to {MAX_ACTIONS} items")
    try:
        size = len(json.dumps(actions, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("actions must be JSON serializable") from exc
    if size > MAX_ACTION_BYTES:
        raise ValueError("action batch is too large")

    prepared: list[dict[str, Any]] = []
    for raw in actions:
        if not isinstance(raw, dict):
            raise ValueError("each action must be an object")
        action_type = _clean_string(raw.get("type"), "type", limit=40, required=True)
        allowed = _ALLOWED_FIELDS.get(action_type)
        if allowed is None:
            raise ValueError(f"unsupported monitoring action: {action_type!r}")
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unknown fields for {action_type}: {', '.join(sorted(unknown))}")

        if action_type == "monitor.upsert":
            company = _clean_string(raw.get("company"), "company", limit=200, required=True)
            provider = _clean_string(raw.get("provider"), "provider", limit=40).lower()
            slug = _clean_string(raw.get("slug"), "slug", limit=200)
            careers_url = _clean_url(raw.get("careers_url"))
            status = _clean_string(raw.get("status") or "active", "status", limit=20)
            job_id = _clean_string(raw.get("job_id"), "job_id", limit=200)
            if job_id and store.get_job(job_id) is None:
                raise ValueError(f"unknown job: {job_id}")
            resolution = ats.resolve_board_result(
                company, provider=provider or None, slug=slug or None,
                careers_url=careers_url, probe=False,
                inspect_careers_page=False,
            )
            prepared.append({
                "type": action_type,
                "company": resolution.company or company,
                "provider": resolution.provider,
                "slug": resolution.slug,
                "careers_url": resolution.careers_url or careers_url,
                "resolution_status": resolution.status.value,
                "status": status,
                "job_id": job_id,
            })
        elif action_type == "monitor.status":
            monitor_id = _clean_string(raw.get("monitor_id"), "monitor_id", limit=100, required=True)
            if store.get_company_monitor(monitor_id) is None:
                raise ValueError(f"unknown monitor: {monitor_id}")
            prepared.append({
                "type": action_type, "monitor_id": monitor_id,
                "status": _clean_string(raw.get("status"), "status", limit=20, required=True),
            })
        elif action_type in {"monitor.scan", "monitor.contacts"}:
            monitor_id = _clean_string(raw.get("monitor_id"), "monitor_id", limit=100, required=True)
            if store.get_company_monitor(monitor_id) is None:
                raise ValueError(f"unknown monitor: {monitor_id}")
            prepared.append({"type": action_type, "monitor_id": monitor_id})
        elif action_type in {"application.restore", "application.note"}:
            job_id = _clean_string(raw.get("job_id"), "job_id", limit=240, required=True)
            include_tombstoned = action_type == "application.restore"
            if store.get_application(job_id, include_tombstoned=include_tombstoned) is None:
                raise ValueError(f"unknown application: {job_id}")
            if action_type == "application.restore":
                prepared.append({"type": action_type, "job_id": job_id})
            else:
                when = _clean_string(raw.get("when"), "when", limit=10, required=True)
                try:
                    dt.date.fromisoformat(when)
                except ValueError as exc:
                    raise ValueError("when must be an ISO date (YYYY-MM-DD)") from exc
                prepared.append({
                    "type": action_type,
                    "job_id": job_id,
                    "text": _clean_string(raw.get("text"), "text", limit=500, required=True),
                    "when": when,
                })
        else:
            prepared.append({
                "type": action_type,
                "job_id": _clean_string(raw.get("job_id"), "job_id", limit=200, required=True),
                "state": _clean_string(raw.get("state"), "state", limit=20, required=True),
            })
    return prepared


def apply_actions(cfg: dict, store, actions: Any, *, initiator: str = "user") -> dict[str, Any]:
    """Validate the full batch, commit mutations atomically, then perform scans."""
    prepared = _prepare_actions(cfg, store, actions)
    results: list[dict[str, Any]] = []
    scan_ids: list[str] = []
    contact_ids: list[str] = []
    restore_ids = [
        action["job_id"] for action in prepared
        if action["type"] == "application.restore"
    ]
    recoverable_restore_ids = [
        job_id for job_id in restore_ids
        if (store.get_application(job_id, include_tombstoned=True) or {}).get("tombstoned_at")
    ]
    restore_run = (
        store.begin_reconciliation_run("restore", initiator)
        if recoverable_restore_ids else None
    )
    restored_count = 0
    try:
        with store.conn:
            for action in prepared:
                action_type = action["type"]
                if action_type == "monitor.upsert":
                    company = store._upsert_company_monitor(
                        action["company"], provider=action["provider"], slug=action["slug"],
                        careers_url=action["careers_url"], status=action["status"],
                        resolution_status=action["resolution_status"], added_from="user",
                    )
                    if action["job_id"]:
                        store._link_monitor_job(company["id"], action["job_id"])
                        existing = store.get_job_review(action["job_id"])
                        store._set_job_review(
                            action["job_id"], existing["state"] if existing else "pending",
                            ["monitored"],
                        )
                    results.append(company)
                elif action_type == "monitor.status":
                    results.append(store._set_company_monitor_status(
                        action["monitor_id"], action["status"],
                    ))
                elif action_type == "review.set":
                    results.append(store._set_job_review(
                        action["job_id"], action["state"], (),
                    ))
                elif action_type == "application.restore":
                    if restore_run is None:
                        result = {"ok": True, "restored": False, "run_id": ""}
                    else:
                        from jobscope.apply import recovery
                        result = recovery._restore_application_in_run(
                            store, action["job_id"], restore_run["id"],
                        )
                    results.append(result)
                    restored_count += int(result["restored"])
                elif action_type == "application.note":
                    results.append({
                        "ok": True,
                        "job_id": action["job_id"],
                        "added": store._append_note(
                            action["job_id"], action["text"], when=action["when"],
                        ),
                    })
                elif action_type == "monitor.contacts":
                    contact_ids.append(action["monitor_id"])
                else:
                    scan_ids.append(action["monitor_id"])
            if restore_run is not None:
                store._finalize_reconciliation_run(
                    restore_run["id"], restored=restored_count,
                )
    except Exception:
        if restore_run is not None:
            store.fail_reconciliation_run(restore_run["id"], "transaction_failed")
        raise
    scans = []
    for monitor_id in scan_ids:
        current = store.get_company_monitor(monitor_id)
        if current["resolution_status"] == "unresolved":
            current = monitor.resolve_monitor(store, current, probe=True)
        scans.append(monitor.scan_monitor(
            cfg, store, current, include_contacts=False,
        ))
    contacts = [
        monitor.refresh_monitor_contacts(
            cfg, store, store.get_company_monitor(monitor_id), force=True,
        )
        for monitor_id in contact_ids
    ]
    from jobscope.deliver.render import (
        _activity_audit_data,
        _application_records,
        _companies_data,
        _reviews_data,
    )
    response = {
        "ok": True,
        "applied": len(results),
        "results": results,
        "scans": scans,
        "contacts": contacts,
        "companies": _companies_data(store),
        "reviews": _reviews_data(store),
        "applications": _application_records(store),
        "activity_audit": _activity_audit_data(store),
    }
    if scan_ids:
        from jobscope.deliver.render import build_data
        response["rows"] = build_data(cfg, store)["rows"]
    return response


def resolve_company(cfg: dict, store, *, company: str, careers_url: str = "",
                    provider: str = "", slug: str = "", limit: int = 20) -> dict[str, Any]:
    """Preview resolution and ranked openings without creating a monitor."""
    company = _clean_string(company, "company", limit=200, required=True)
    careers_url = _clean_url(careers_url)
    resolution = ats.resolve_board_result(
        company, provider=provider or None, slug=slug or None,
        careers_url=careers_url, probe=True,
    )
    response: dict[str, Any] = {
        "ok": resolution.resolved,
        "company": resolution.company or company,
        "status": resolution.status.value,
        "provider": resolution.provider,
        "slug": resolution.slug,
        "careers_url": resolution.careers_url or careers_url,
        "detail": resolution.detail,
        "count": 0,
        "matched": 0,
        "results": [],
    }
    if not resolution.resolved:
        return response
    fetch = ats.fetch_company_result(response["company"], resolution.provider, resolution.slug)
    response["source_status"] = fetch.status.value
    response["detail"] = fetch.detail
    response["count"] = len(fetch.jobs)
    if not fetch.successful:
        response["ok"] = False
        return response
    candidates = ats.filter_profile_jobs(cfg, store, fetch.jobs)
    candidates = ats.hydrate_company_jobs(resolution.provider, candidates)
    scored = score_jobs(cfg, store, candidates)
    matches = [item for item in scored if item.tier != "Skip"][:max(1, min(int(limit), 50))]
    response["matched"] = len(matches)
    response["results"] = [{
        "id": item.job.id,
        "title": item.job.title,
        "location": item.job.location,
        "url": item.job.url,
        "score": round(item.score, 1),
        "tier": item.tier,
        "rationale": item.rationale,
    } for item in matches]
    return response


def run_actions_file(cfg: dict, store, path: str) -> int:
    """Apply a JSON action list from a trusted local/workflow file path."""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  could not read monitoring actions: {exc}")
        return 1
    actions = payload.get("actions") if isinstance(payload, dict) else payload
    try:
        result = apply_actions(cfg, store, actions, initiator="cloud_refresh")
    except ValueError as exc:
        print(f"  invalid monitoring actions: {exc}")
        return 1
    print(
        f"  applied {result['applied']} monitoring change(s); "
        f"ran {len(result['scans'])} requested scan(s)"
    )
    return 0