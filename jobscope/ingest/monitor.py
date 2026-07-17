"""Persistent company-monitor seeding and scanning orchestration."""
from __future__ import annotations

from typing import Any

from jobscope.analyze.review import persist_scored_job, score_jobs
from jobscope.ingest import ats

SEED_MARKER = "company-monitoring:seeded-v1"
SUPPORTED_PROVIDERS = ats.SUPPORTED_PROVIDERS


def board_url(provider: str, slug: str) -> str:
    return ats.board_url(provider, slug)


def _seed_entry(store, entry: str, *, origin: str) -> dict[str, Any]:
    resolved = ats.resolve_config_entry(entry)
    if resolved is None:
        return store._upsert_company_monitor(
            entry, resolution_status="unresolved", added_from=origin,
        )
    company, provider, slug = resolved
    resolution = "resolved" if provider in SUPPORTED_PROVIDERS else "unsupported"
    return store._upsert_company_monitor(
        company,
        provider=provider,
        slug=slug,
        careers_url=board_url(provider, slug),
        resolution_status=resolution,
        added_from=origin,
    )


def seed_monitors(cfg: dict, store, *, force: bool = False) -> dict[str, Any]:
    """Import configured monitors and retire legacy application-only monitors.

    The first migration also preserves the pre-monitoring dashboard shortlist by
    marking its visible un-applied jobs as ``saved`` legacy reviews. ``force``
    reimports monitor origins but never repeats that legacy-review conversion.
    """
    already_seeded = bool(store.meta_get(SEED_MARKER))
    # Run on every seed so obsolete clients cannot reactivate application history.
    archived_known = store.archive_application_only_monitors()
    if already_seeded and not force:
        return {
            "seeded": False,
            "already_seeded": True,
            "configured": 0,
            "applications": 0,
            "archived_known": archived_known,
            "legacy_saved": 0,
            "total": len(store.list_company_monitors()),
        }

    configured_entries = [
        str(entry).strip() for entry in (cfg.get("search", {}) or {}).get("companies", [])
        if str(entry).strip()
    ]
    application_companies = store.active_application_companies(limit=1000)
    configured_ids: set[str] = set()
    legacy_saved = 0

    with store.conn:
        for entry in configured_entries:
            configured_ids.add(_seed_entry(store, entry, origin="config")["id"])

        if not already_seeded:
            applied_job_ids = {
                application["job_id"] for application in store.applications()
                if application.get("job_id")
            }
            for job in store.jobs(order_by_score=False):
                if (job.id in applied_job_ids or (job.status or "open") != "open" or
                        (job.tier or "Skip") == "Skip"):
                    continue
                store._set_job_review(job.id, "saved", ["legacy"])
                legacy_saved += 1
        store.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (SEED_MARKER, "1"),
        )

    return {
        "seeded": True,
        "already_seeded": already_seeded,
        "configured": len(configured_ids),
        "applications": len(application_companies),
        "archived_known": archived_known,
        "legacy_saved": legacy_saved,
        "total": len(store.list_company_monitors()),
    }


def run_seed(cfg: dict, store, *, force: bool = False) -> int:
    result = seed_monitors(cfg, store, force=force)
    if result["already_seeded"] and not result["seeded"]:
        archived = result["archived_known"]
        detail = f"; {archived} application-only archived" if archived else ""
        print(f"  company monitors already seeded ({result['total']} watching{detail})")
        return 0
    print(
        "  seeded company monitors: "
        f"{result['configured']} configured, {result['applications']} known from applications, "
        f"{result['archived_known']} application-only archived, "
        f"{result['legacy_saved']} legacy roles saved ({result['total']} total)"
    )
    return 0


def run_list(store, *, include_removed: bool = False) -> int:
    monitors = store.list_company_monitors(include_removed=include_removed)
    if not monitors:
        print("  no monitored companies")
        return 0
    for monitor in monitors:
        board = (
            f"{monitor['provider']}/{monitor['slug']}"
            if monitor["provider"] and monitor["slug"] else monitor["resolution_status"]
        )
        print(f"  {monitor['company']} [{monitor['status']}] {board}")
    return 0


def resolve_monitor(store, monitor: dict[str, Any], *, probe: bool = True) -> dict[str, Any]:
    """Resolve and persist one unresolved monitor using its name/portal URL."""
    resolution = ats.resolve_board_result(
        monitor["company"],
        provider=monitor.get("provider") or None,
        slug=monitor.get("slug") or None,
        careers_url=monitor.get("careers_url") or "",
        probe=probe,
    )
    return store.upsert_company_monitor(
        resolution.company or monitor["company"],
        provider=resolution.provider,
        slug=resolution.slug,
        careers_url=resolution.careers_url or monitor.get("careers_url", ""),
        status=monitor["status"],
        resolution_status=resolution.status.value,
        added_from=(monitor.get("origins") or ["user"])[0],
    )


def scan_monitor(
    cfg: dict, store, monitor: dict[str, Any], *, refresh_contacts: bool = False,
    include_contacts: bool = True,
) -> dict[str, Any]:
    """Fetch, score, link, and safely reconcile one active resolved monitor."""
    result = {
        "ok": False,
        "monitor_id": monitor["id"],
        "company": monitor["company"],
        "board_count": 0,
        "matched": 0,
        "new": 0,
        "closed": 0,
        "status": "",
        "error": "",
        "contact_status": "not-run",
        "contact_domain": "",
        "recruiter_count": 0,
        "recruiter": None,
        "contact_error": "",
    }
    if monitor.get("status") != "active":
        result["status"] = "paused"
        result["error"] = "monitor is not active"
        return result

    if include_contacts:
        contact_result = refresh_monitor_contacts(
            cfg, store, monitor, force=refresh_contacts,
        )
        for key in (
            "contact_status", "contact_domain", "recruiter_count",
            "recruiter", "contact_error",
        ):
            result[key] = contact_result[key]

    if monitor.get("resolution_status") != "resolved" or not monitor.get("provider") or not monitor.get("slug"):
        result["status"] = monitor.get("resolution_status") or "unresolved"
        result["error"] = "company monitor needs a supported career portal"
        return result

    fetch = ats.fetch_company_result(monitor["company"], monitor["provider"], monitor["slug"])
    result["status"] = fetch.status.value
    result["board_count"] = len(fetch.jobs)
    store.set_source_health(
        f"monitor:{monitor['id']}",
        provider=monitor["provider"],
        slug=monitor["slug"],
        status=fetch.status.value,
        item_count=len(fetch.jobs),
        attempts=fetch.attempts,
        status_code=fetch.status_code,
        detail=fetch.detail,
    )
    if not fetch.successful:
        result["error"] = fetch.detail or fetch.status.value
        return result

    try:
        scored = score_jobs(cfg, store, ats.filter_board_jobs(cfg, fetch.jobs))
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    for item in scored:
        if item.tier == "Skip" or not item.job.title or not item.job.company:
            continue
        if persist_scored_job(store, item):
            result["new"] += 1
        store.link_monitor_job(monitor["id"], item.job.id)
        store.ensure_job_review(item.job.id, origins=["monitored"])
        result["matched"] += 1

    if fetch.status == ats.BoardStatus.OK and fetch.jobs:
        result["closed"] = store.reconcile_monitor_jobs(
            monitor["id"], {job.id for job in fetch.jobs},
        )
    store.mark_monitor_success(monitor["id"])
    result["ok"] = True
    return result


def refresh_monitor_contacts(
    cfg: dict, store, monitor: dict[str, Any], *, force: bool = True,
) -> dict[str, Any]:
    """Refresh one monitor's recruiter contacts without fetching its job board."""
    result = {
        "ok": False,
        "monitor_id": monitor["id"],
        "company": monitor["company"],
        "contact_status": "not-run",
        "contact_domain": "",
        "recruiter_count": 0,
        "recruiter": None,
        "contact_error": "",
    }
    try:
        from jobscope.apply import outreach
        contact_result = outreach.refresh_company_contacts(
            cfg, store, monitor["company"],
            url=monitor.get("careers_url") or "",
            force=force,
        )
        contact_status = contact_result["status"]
        failure_detail = {
            "disabled": "recruiter lookup is disabled in configuration",
            "unresolved": "could not confirm a company domain",
        }.get(contact_status, "")
        result.update({
            "ok": contact_status in {"fresh", "updated", "preserved"},
            "contact_status": contact_status,
            "contact_domain": contact_result["domain"],
            "recruiter_count": len(contact_result["contacts"]),
            "recruiter": contact_result["recruiter"],
            "contact_error": failure_detail,
        })
    except Exception as exc:  # recruiter discovery is optional
        result["contact_status"] = "error"
        result["contact_error"] = str(exc)[:200]
    return result


def scan_active_monitors(cfg: dict, store) -> dict[str, Any]:
    """Seed once, then scan resolved active monitors."""
    seed_monitors(cfg, store)
    results: list[dict[str, Any]] = []
    active = store.list_company_monitors(status="active")
    unresolved = [item for item in active if item["resolution_status"] != "resolved"]
    contact_settings = (
        (cfg.get("apply", {}).get("outreach", {}) or {}).get("monitor_scan", {}) or {}
    )
    refresh_contacts = bool(contact_settings.get("scheduled", False))
    for current in active:
        if current["resolution_status"] == "resolved":
            results.append(scan_monitor(
                cfg, store, current, refresh_contacts=refresh_contacts,
            ))
    return {
        "companies": len(results),
        "needs_setup": len(unresolved),
        "unresolved": [item["company"] for item in unresolved],
        "successful": sum(1 for result in results if result["ok"]),
        "matched": sum(int(result["matched"]) for result in results),
        "new": sum(int(result["new"]) for result in results),
        "closed": sum(int(result["closed"]) for result in results),
        "results": results,
    }


def run_scan(cfg: dict, store, company: str | None = None) -> int:
    if company:
        current = store.get_company_monitor(company)
        if current is None:
            print(f"  no monitor found for {company!r}")
            return 1
        if current["resolution_status"] == "unresolved":
            current = resolve_monitor(store, current)
        results = [scan_monitor(cfg, store, current, refresh_contacts=True)]
    else:
        summary = scan_active_monitors(cfg, store)
        results = summary["results"]
        if summary["needs_setup"]:
            print(
                f"  {summary['needs_setup']} company monitor(s) need portal setup: "
                + ", ".join(summary["unresolved"][:8])
            )
    for result in results:
        if result["ok"]:
            print(
                f"  {result['company']}: {result['board_count']} on board, "
                f"{result['matched']} matched ({result['new']} new, {result['closed']} closed)"
            )
        else:
            print(f"  {result['company']}: {result['status']} -- {result['error']}")
    return 0 if all(result["ok"] for result in results) else 1