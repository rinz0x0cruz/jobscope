"""Job scraping via JobSpy (LinkedIn / Indeed / Glassdoor / Google / ZipRecruiter).

Thin, defensive wrapper: run each configured term/source in committed pages of
ten, normalize JobSpy rows into `Job` objects, and upsert them (dedupe and
first/last-seen are handled by the store). Durable cursors resume the next page;
failures are isolated so one bad source doesn't sink the run.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any

from jobscope.core import geo
from jobscope.core.model import Job, derive_remote_scope
from jobscope.core.store import now_iso
from jobscope.ingest.ats import _strip_html

DISCOVERY_MARKER = "discovery:last_scan"
DISCOVERY_CURSOR_MARKER = "discovery:cursors:v1"
DISCOVERY_PAGE_SIZE = 10
_CURSOR_DONE = "done"


def _load_cursors(store) -> dict[str, int | str]:
    raw = store.meta_get(DISCOVERY_CURSOR_MARKER)
    if not raw:
        return {}
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(values, dict):
        return {}
    return {
        str(key): value
        for key, value in values.items()
        if value == _CURSOR_DONE
        or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
    }


def _save_cursors(store, cursors: dict[str, int | str]) -> None:
    store.meta_set(
        DISCOVERY_CURSOR_MARKER,
        json.dumps(cursors, sort_keys=True, separators=(",", ":")),
    )


def _cursor_key(settings: dict, term: str, site: str) -> str:
    query = {
        "site": site,
        "term": term,
        "google_term": settings.get("google_term") or term,
        "location": settings.get("location") or "",
        "country_indeed": settings.get("country_indeed", "USA"),
        "distance": settings.get("distance", 50),
        "hours_old": settings.get("hours_old") or 0,
        "is_remote": bool(settings.get("is_remote")),
        "job_type": settings.get("job_type") or "",
    }
    encoded = json.dumps(query, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def discovery_due(cfg: dict, store, *, now: _dt.datetime | None = None) -> bool:
    settings = cfg.get("discovery", {}) or {}
    if not settings.get("enabled", True):
        return False
    if store.meta_get(DISCOVERY_CURSOR_MARKER) not in (None, "", "{}"):
        return True
    interval = max(1, int(settings.get("interval_hours", 24) or 24))
    last = store.meta_get(DISCOVERY_MARKER)
    if not last:
        return True
    try:
        previous = _dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    current = now or _dt.datetime.now(_dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_dt.timezone.utc)
    return current - previous >= _dt.timedelta(hours=interval)


def run(cfg: dict, store, *, mode: str = "all", force_discovery: bool = False) -> int:
    if mode not in {"all", "monitored", "discovery"}:
        raise ValueError(f"invalid scan mode: {mode}")
    if mode in {"all", "monitored"}:
        from . import monitor
        summary = monitor.scan_active_monitors(cfg, store)
        print(
            "  monitored portals: "
            f"{summary['successful']}/{summary['companies']} healthy, "
            f"{summary['matched']} matched ({summary['new']} new)"
        )
    if mode == "monitored":
        return 0
    if not force_discovery and not discovery_due(cfg, store):
        print("  broad discovery not due yet; monitored portals were still checked.")
        return 0
    if not (cfg.get("discovery", {}) or {}).get("enabled", True):
        print("  broad discovery is disabled.")
        return 0

    base = cfg["search"]
    # An editable, résumé-derived named profile (data/profiles/) drives the
    # fetch when present; config.search is the fallback. See analyze/profile.py.
    from jobscope.analyze import profile as _profile
    prof = _profile.load(cfg)
    if prof:
        base = _profile.apply_to_search(base, prof)
        terms = base.get("terms") or []
        locs = base.get("profiles") or []
        print("  search profile active: "
              f"{len(terms)} role(s)" + (f" x {len(locs)} location(s)" if locs else "")
              + (f" -> {', '.join(terms[:6])}" if terms else ""))
    default_home = base.get("home_country", "India")
    geo_on = bool(base.get("scope_to_home", True))
    total_new = 0
    total_seen = 0
    total_dropped = 0
    cursors = _load_cursors(store)
    active_cursors: set[str] = set()
    pages_remaining = False

    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("  JobSpy is not installed. Run: pip install python-jobspy")
        return 1

    # One search per profile; each profile overrides the base search (location,
    # is_remote, hours_old, ...). No profiles -> a single search from the base.
    profiles = base.get("profiles") or [{}]
    for search_profile in profiles:
        settings = {**base, **search_profile}
        home = settings.get("home_country", default_home)
        label = search_profile.get("name") or settings.get("location") or "search"
        if len(profiles) > 1:
            print(f"\n  == profile: {label} "
                  f"(location={settings.get('location')!r}, hours_old={settings.get('hours_old')}) ==")
        new, seen, dropped, pending = _scan_profile(
            scrape_jobs, settings, store, label, home, geo_on,
            cursors, active_cursors,
        )
        total_new += new
        total_seen += seen
        total_dropped += dropped
        pages_remaining = pages_remaining or pending

    cursors = {key: value for key, value in cursors.items() if key in active_cursors}
    if pages_remaining:
        _save_cursors(store, cursors)
    else:
        store.meta_set(DISCOVERY_MARKER, now_iso())
        _save_cursors(store, {})

    drop_note = f" ({total_dropped} out-of-scope dropped)" if total_dropped else ""
    if pages_remaining:
        print(f"\n  broad discovery page complete: {total_new} new / {total_seen} seen{drop_note}. "
              "More pages are ready; run scan again to resume.")
    else:
        print(f"\n  broad discovery complete: {total_new} new / {total_seen} seen{drop_note}. "
              "Next: python -m jobscope match")
    return 0


def _scan_profile(scrape_jobs, s: dict, store, label: str,
                  home: str, geo_on: bool, cursors: dict[str, int | str],
                  active_cursors: set[str]) -> tuple[int, int, int, bool]:
    """Run one page per term/source; return counts plus whether work remains."""
    new_total = 0
    seen_total = 0
    dropped_total = 0
    pages_remaining = False
    sites = s.get("sites") or []
    if isinstance(sites, str):
        sites = [sites]
    try:
        result_limit = max(1, int(s.get("results_wanted") or DISCOVERY_PAGE_SIZE))
    except (TypeError, ValueError):
        result_limit = DISCOVERY_PAGE_SIZE
    for term in s["terms"]:
        for site_value in sites:
            site = str(site_value)
            cursor_key = _cursor_key(s, term, site)
            active_cursors.add(cursor_key)
            cursor = cursors.get(cursor_key, 0)
            if cursor == _CURSOR_DONE:
                continue
            offset = int(cursor)
            if offset >= result_limit:
                cursors[cursor_key] = _CURSOR_DONE
                _save_cursors(store, cursors)
                continue
            page_size = min(DISCOVERY_PAGE_SIZE, result_limit - offset)
            source = f"jobspy:{site}:{label}:{term}"
            action = f"scan:{site}:{label}:{term}"
            try:
                kwargs: dict[str, Any] = dict(
                site_name=site,
                search_term=term,
                google_search_term=s.get("google_term") or term,
                location=s["location"],
                results_wanted=page_size,
                offset=offset,
                country_indeed=s.get("country_indeed", "USA"),
                distance=s.get("distance", 50),
                description_format="html",
                linkedin_fetch_description=s.get("linkedin_fetch_description", True),
                verbose=0,
            )
                # Optional proxies protect your main IP on big scans (no fake accounts).
                if s.get("proxies"):
                    kwargs["proxies"] = s["proxies"]
                # Indeed/LinkedIn only allow one of hours_old vs is_remote/job_type;
                # prefer recency and let the location string handle work mode.
                if s.get("hours_old"):
                    kwargs["hours_old"] = s["hours_old"]
                elif s.get("is_remote"):
                    kwargs["is_remote"] = True

                df = scrape_jobs(**kwargs)
                result_count = min(len(df), page_size) if df is not None else 0
                new_here = 0
                if df is not None:
                    for index, (_, row) in enumerate(df.iterrows()):
                        if index >= page_size:
                            break
                        job = _row_to_job(row)
                        if not (job.title and job.company):
                            continue
                        if job.is_remote and not bool(s.get("is_remote", True)):
                            dropped_total += 1
                            continue
                        if geo_on and not geo.in_scope(job, home):
                            dropped_total += 1
                            continue
                        seen_total += 1
                        if store.upsert_job(job):
                            new_here += 1
                new_total += new_here

                page_full = result_count >= page_size
                next_offset = offset + page_size
                has_more = page_full and next_offset < result_limit
                cursors[cursor_key] = next_offset if has_more else _CURSOR_DONE
                _save_cursors(store, cursors)
                pages_remaining = pages_remaining or has_more

                if result_count == 0:
                    status = "empty" if offset == 0 else "ok"
                elif has_more:
                    status = "paged"
                elif page_full and next_offset >= result_limit:
                    status = "saturated"
                else:
                    status = "ok"
                detail = ""
                if has_more:
                    detail = f"page at offset {offset} complete; next offset {next_offset}"
                elif status == "saturated":
                    detail = "configured result cap reached; additional results may exist"
                cap_note = ", more pages available" if has_more else (
                    ", result cap reached" if status == "saturated" else ""
                )
                print(f"  [{site}:{term}] {result_count} results "
                      f"({new_here} new, offset {offset}{cap_note})")
                store.log_run(action, result_count, status)
                store.set_source_health(
                    source, provider="jobspy", slug=term,
                    status=status, item_count=result_count, attempts=1,
                    detail=detail,
                )
            except Exception as e:  # noqa: BLE001 - keep scanning other terms
                cursors[cursor_key] = offset
                _save_cursors(store, cursors)
                pages_remaining = True
                print(f"  [{site}:{term}] error at offset {offset}: {e}")
                store.log_run(action, 0, "error")
                store.set_source_health(
                    source, provider="jobspy", slug=term,
                    status="error", item_count=0, attempts=1, detail=str(e),
                )
    return new_total, seen_total, dropped_total, pages_remaining


def _val(row, *names, default=None):
    """Fetch the first present, non-NaN column value from a pandas row."""
    try:
        import pandas as pd
        isna = pd.isna
    except ImportError:  # pragma: no cover
        isna = lambda v: v is None  # noqa: E731
    for n in names:
        if n in row:
            v = row[n]
            try:
                if v is not None and not (isinstance(v, float) and isna(v)):
                    return v
            except (TypeError, ValueError):
                return v
    return default


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# Positive remote signals. JobSpy's `is_remote` flag alone over-reports (it marks
# on-site roles whose description merely mentions "remote"/"hybrid"), so we only
# trust a True when the location/title corroborates it.
_REMOTE_WORDS = ("remote", "anywhere", "work from home", "work-from-home", "wfh",
                 "fully distributed", "distributed team", "telecommute")


def _derive_remote(raw_is_remote: bool, location: str, title: str) -> bool:
    blob = f"{location}\n{title}".lower()
    if any(w in blob for w in _REMOTE_WORDS):
        return True
    # A concrete place (e.g. "Dublin, County Dublin, Ireland") contradicts a bare
    # remote flag; only trust JobSpy's True when no specific location is given.
    if raw_is_remote and "," not in (location or ""):
        return True
    return False


def _row_to_job(row) -> Job:
    raw_remote = _val(row, "is_remote", default=False)
    title = str(_val(row, "title", default="") or "").strip()
    location = str(_val(row, "location", default="") or "").strip()
    is_remote = _derive_remote(bool(raw_remote) if raw_remote is not None else False,
                               location, title)
    job = Job(
        source=str(_val(row, "site", default="") or ""),
        title=title,
        company=str(_val(row, "company", default="") or "").strip(),
        location=location,
        is_remote=is_remote,
        remote_scope=derive_remote_scope(location, title, is_remote),
        raw_is_remote=(bool(raw_remote) if raw_remote is not None else None),
        url=str(_val(row, "job_url", "job_url_direct", default="") or ""),
        description=_strip_html(str(_val(row, "description", default="") or "")),
        salary_min=_num(_val(row, "min_amount")),
        salary_max=_num(_val(row, "max_amount")),
        salary_interval=str(_val(row, "interval", default="") or ""),
        currency=str(_val(row, "currency", default="") or ""),
        job_type=str(_val(row, "job_type", default="") or ""),
        job_level=str(_val(row, "job_level", default="") or ""),
        company_industry=str(_val(row, "company_industry", default="") or ""),
        company_url=str(_val(row, "company_url", default="") or ""),
        date_posted=str(_val(row, "date_posted", default="") or ""),
        first_seen=now_iso(),
        last_seen=now_iso(),
    )
    return job.ensure_id()
