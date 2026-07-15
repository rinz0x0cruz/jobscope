"""Job scraping via JobSpy (LinkedIn / Indeed / Glassdoor / Google / ZipRecruiter).

Thin, defensive wrapper: run each configured search term, normalize the JobSpy
DataFrame rows into `Job` objects, and upsert them (dedupe + first/last-seen is
handled by the store). Failures are per-term so one bad site doesn't sink the run.
"""
from __future__ import annotations

from typing import Any

from jobscope.core import geo
from jobscope.core.model import Job, derive_remote_scope
from jobscope.core.store import now_iso


def run(cfg: dict, store) -> int:
    base = cfg["search"]
    # An editable, résumé-derived search profile (data/profile.yaml) drives the
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
    home = base.get("home_country", "India")
    geo_on = bool(base.get("scope_to_home", True))
    total_new = 0
    total_seen = 0
    total_dropped = 0

    try:
        from jobspy import scrape_jobs
    except ImportError:
        scrape_jobs = None
        if base.get("companies"):
            print("  JobSpy not installed - skipping keyword search, running ATS boards only.")
        else:
            print("  JobSpy is not installed. Run: pip install python-jobspy")
            return 1

    if scrape_jobs is not None:
        # One search per profile; each profile overrides the base search (location,
        # is_remote, hours_old, ...). No profiles -> a single search from the base
        # (backwards compatible).
        profiles = base.get("profiles") or [{}]
        for prof in profiles:
            s = {**base, **prof}
            label = prof.get("name") or s.get("location") or "search"
            if len(profiles) > 1:
                print(f"\n  == profile: {label} "
                      f"(location={s.get('location')!r}, hours_old={s.get('hours_old')}) ==")
            new, seen, dropped = _scan_profile(scrape_jobs, s, store, label, home, geo_on)
            total_new += new
            total_seen += seen
            total_dropped += dropped

    # ATS boards: pull configured companies' public job boards directly. Needs
    # only `requests`, so it runs even when JobSpy is unavailable.
    from . import ats
    total_new += ats.run(cfg, store)

    drop_note = f" ({total_dropped} out-of-scope dropped)" if total_dropped else ""
    print(f"\n  scan complete: {total_new} new / {total_seen} seen{drop_note}. "
          f"Next: python -m jobscope match")
    return 0


def _scan_profile(scrape_jobs, s: dict, store, label: str,
                  home: str = "India", geo_on: bool = True) -> tuple[int, int, int]:
    """Run every search term for one profile; returns (new, seen, dropped) counts."""
    new_total = 0
    seen_total = 0
    dropped_total = 0
    for term in s["terms"]:
        try:
            kwargs: dict[str, Any] = dict(
                site_name=s["sites"],
                search_term=term,
                google_search_term=s.get("google_term") or term,
                location=s["location"],
                results_wanted=s["results_wanted"],
                country_indeed=s.get("country_indeed", "USA"),
                distance=s.get("distance", 50),
                description_format="markdown",
                linkedin_fetch_description=s.get("linkedin_fetch_description", True),
                verbose=0,
            )
            # optional proxies protect your main IP on big scans (no fake accounts)
            if s.get("proxies"):
                kwargs["proxies"] = s["proxies"]
            # Indeed/LinkedIn only allow ONE of {hours_old} vs {is_remote/job_type};
            # prefer recency and let the location string handle remote vs on-site.
            if s.get("hours_old"):
                kwargs["hours_old"] = s["hours_old"]
            elif s.get("is_remote"):
                kwargs["is_remote"] = True

            df = scrape_jobs(**kwargs)
            if df is None or len(df) == 0:
                print(f"  [{term}] 0 results")
                store.log_run(f"scan:{label}:{term}", 0, "empty")
                store.set_source_health(
                    f"jobspy:{label}:{term}", provider="jobspy", slug=term,
                    status="empty", item_count=0, attempts=1,
                )
                continue
            new_here = 0
            for _, row in df.iterrows():
                job = _row_to_job(row)
                if not (job.title and job.company):
                    continue
                if geo_on and not geo.in_scope(job, home):
                    dropped_total += 1
                    continue
                seen_total += 1
                if store.upsert_job(job):
                    new_here += 1
            new_total += new_here
            saturated = len(df) >= int(s.get("results_wanted") or 0) > 0
            status = "saturated" if saturated else "ok"
            cap_note = ", result cap reached" if saturated else ""
            print(f"  [{term}] {len(df)} results ({new_here} new{cap_note})")
            store.log_run(f"scan:{label}:{term}", len(df), status)
            store.set_source_health(
                f"jobspy:{label}:{term}", provider="jobspy", slug=term,
                status=status, item_count=len(df), attempts=1,
                detail=("results_wanted cap reached; additional results may exist"
                        if saturated else ""),
            )
        except Exception as e:  # noqa: BLE001 - keep scanning other terms
            print(f"  [{term}] error: {e}")
            store.log_run(f"scan:{label}:{term}", 0, "error")
            store.set_source_health(
                f"jobspy:{label}:{term}", provider="jobspy", slug=term,
                status="error", item_count=0, attempts=1, detail=str(e),
            )
    return new_total, seen_total, dropped_total


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
        description=str(_val(row, "description", default="") or ""),
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
