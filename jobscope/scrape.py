"""Job scraping via JobSpy (LinkedIn / Indeed / Glassdoor / Google / ZipRecruiter).

Thin, defensive wrapper: run each configured search term, normalize the JobSpy
DataFrame rows into `Job` objects, and upsert them (dedupe + first/last-seen is
handled by the store). Failures are per-term so one bad site doesn't sink the run.
"""
from __future__ import annotations

from typing import Any

from .model import Job
from .store import now_iso


def run(cfg: dict, store) -> int:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("  JobSpy is not installed. Run: pip install python-jobspy")
        return 1

    s = cfg["search"]
    total_new = 0
    total_seen = 0
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
                linkedin_fetch_description=s.get("linkedin_fetch_description", False),
                verbose=0,
            )
            # optional proxies protect your main IP on big scans (no fake accounts)
            if s.get("proxies"):
                kwargs["proxies"] = s["proxies"]
            # Indeed/LinkedIn only allow ONE of {hours_old} vs {is_remote/job_type};
            # prefer recency and let matching handle the remote preference.
            if s.get("hours_old"):
                kwargs["hours_old"] = s["hours_old"]
            elif s.get("is_remote"):
                kwargs["is_remote"] = True

            df = scrape_jobs(**kwargs)
            if df is None or len(df) == 0:
                print(f"  [{term}] 0 results")
                continue
            new_here = 0
            for _, row in df.iterrows():
                job = _row_to_job(row)
                if not (job.title and job.company):
                    continue
                total_seen += 1
                if store.upsert_job(job):
                    new_here += 1
            total_new += new_here
            print(f"  [{term}] {len(df)} results ({new_here} new)")
            store.log_run(f"scan:{term}", len(df), "ok")
        except Exception as e:  # noqa: BLE001 - keep scanning other terms
            print(f"  [{term}] error: {e}")
            store.log_run(f"scan:{term}", 0, "error")

    print(f"\n  scan complete: {total_new} new / {total_seen} seen. "
          f"Next: python -m jobscope match")
    return 0


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


def _row_to_job(row) -> Job:
    is_remote = _val(row, "is_remote", default=False)
    job = Job(
        source=str(_val(row, "site", default="") or ""),
        title=str(_val(row, "title", default="") or "").strip(),
        company=str(_val(row, "company", default="") or "").strip(),
        location=str(_val(row, "location", default="") or "").strip(),
        is_remote=bool(is_remote) if is_remote is not None else False,
        url=str(_val(row, "job_url", "job_url_direct", default="") or ""),
        description=str(_val(row, "description", default="") or ""),
        salary_min=_num(_val(row, "min_amount")),
        salary_max=_num(_val(row, "max_amount")),
        salary_interval=str(_val(row, "interval", default="") or ""),
        currency=str(_val(row, "currency", default="") or ""),
        job_type=str(_val(row, "job_type", default="") or ""),
        company_industry=str(_val(row, "company_industry", default="") or ""),
        company_url=str(_val(row, "company_url", default="") or ""),
        date_posted=str(_val(row, "date_posted", default="") or ""),
        first_seen=now_iso(),
        last_seen=now_iso(),
    )
    return job.ensure_id()
