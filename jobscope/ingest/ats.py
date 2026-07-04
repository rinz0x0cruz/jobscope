"""Company-targeted fetching from public ATS job boards (Greenhouse / Lever / Ashby).

These boards expose a company's *published* jobs as JSON with **no auth and no
key**. That surfaces roles at specific well-funded companies (e.g. unicorns) that
keyword scraping on LinkedIn/Indeed rarely ranks into view -- you pull the board
directly and filter by location + role, instead of hoping the company ranks in a
generic search.

Every fetch is best-effort (a bad slug or a dead board just yields nothing), so
one company never breaks a scan.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import re
from typing import Any

from jobscope.core import geo, httpx
from jobscope.core.model import Job, derive_remote_scope
from jobscope.core.store import now_iso

# Curated company -> (provider, board slug). Slugs are the board token in the
# careers URL (usually the lowercased company name). Extend freely; unknown or
# wrong slugs simply return nothing. Some big enterprises on Workday (CrowdStrike,
# Palo Alto Networks, SentinelOne) aren't here -- Workday has no simple public
# board API.
COMPANY_BOARDS: dict[str, tuple[str, str]] = {
    "databricks": ("greenhouse", "databricks"),
    "stripe": ("greenhouse", "stripe"),
    "airbnb": ("greenhouse", "airbnb"),
    "coinbase": ("greenhouse", "coinbase"),
    "gitlab": ("greenhouse", "gitlab"),
    "robinhood": ("greenhouse", "robinhood"),
    "brex": ("greenhouse", "brex"),
    "discord": ("greenhouse", "discord"),
    "figma": ("greenhouse", "figma"),
    "samsara": ("greenhouse", "samsara"),
    "anduril": ("greenhouse", "andurilindustries"),
    "wiz": ("greenhouse", "wizinc"),
    "sysdig": ("lever", "sysdig"),
    "elastic": ("greenhouse", "elastic"),
    "cockroachlabs": ("greenhouse", "cockroachlabs"),
    "cloudflare": ("greenhouse", "cloudflare"),
    "mongodb": ("greenhouse", "mongodb"),
    "gusto": ("greenhouse", "gusto"),
    "rubrik": ("greenhouse", "rubrik"),
    "postman": ("greenhouse", "postman"),
    "chainguard": ("greenhouse", "chainguard"),
    "mistral": ("lever", "mistral"),
    "ramp": ("ashby", "ramp"),
    "notion": ("ashby", "notion"),
    "openai": ("ashby", "openai"),
    # --- data / infra / security companies (slugs validated 2026-07) ---
    "snowflake": ("ashby", "snowflake"),
    "datadog": ("greenhouse", "datadog"),
    "okta": ("greenhouse", "okta"),
    "zscaler": ("greenhouse", "zscaler"),
    "confluent": ("ashby", "confluent"),
    "clickhouse": ("greenhouse", "clickhouse"),
    "fivetran": ("greenhouse", "fivetran"),
    "vanta": ("ashby", "vanta"),
    "netskope": ("greenhouse", "netskope"),
    "grafanalabs": ("greenhouse", "grafanalabs"),
    "vercel": ("greenhouse", "vercel"),
    "abnormal": ("greenhouse", "abnormalsecurity"),
    "drata": ("ashby", "drata"),
    "temporal": ("ashby", "temporal"),
    "huntress": ("greenhouse", "huntress"),
    "semgrep": ("ashby", "semgrep"),
    "render": ("ashby", "render"),
    "tines": ("greenhouse", "tines"),
    "material": ("ashby", "materialsecurity"),
    "orca": ("greenhouse", "orcasecurity"),
}


def _strip_html(s: str) -> str:
    s = s or ""
    # Drop the CONTENTS of <style>/<script> blocks and HTML comments before
    # removing tags -- their inner CSS/JS is not readable text and would
    # otherwise leak into snippets/summaries for HTML emails.
    s = re.sub(r"(?is)<(style|script)\b[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _ms_to_date(ms: Any) -> str:
    try:
        return _dt.datetime.fromtimestamp(int(ms) / 1000, _dt.timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def _mk(company: str, title: str, location: str, url: str, desc: str, date_posted: str) -> Job:
    loc = (location or "").strip()
    job = Job(
        source="ats",
        title=(title or "").strip(),
        company=company,
        location=loc,
        is_remote="remote" in loc.lower(),
        url=(url or "").strip(),
        description=desc or "",
        date_posted=(date_posted or "")[:10],
        first_seen=now_iso(),
        last_seen=now_iso(),
    )
    job.remote_scope = derive_remote_scope(loc, title, job.is_remote)
    return job.ensure_id()


def _greenhouse(company: str, slug: str) -> list[Job]:
    data = httpx.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                          params={"content": "true"})
    jobs = (data or {}).get("jobs") or []
    out = []
    for j in jobs:
        loc = ((j.get("location") or {}).get("name") or "")
        out.append(_mk(company, j.get("title", ""), loc, j.get("absolute_url", ""),
                       _strip_html(j.get("content", "")), str(j.get("updated_at", ""))))
    return out


def _lever(company: str, slug: str) -> list[Job]:
    data = httpx.get_json(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    out = []
    for j in (data or []):
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        wt = (j.get("workplaceType") or "").lower()
        desc = j.get("descriptionPlain") or _strip_html(j.get("description", ""))
        job = _mk(company, j.get("text", ""), loc, j.get("hostedUrl", ""),
                  desc, _ms_to_date(j.get("createdAt")))
        if wt == "remote":
            job.is_remote = True
            job.remote_scope = derive_remote_scope(job.location, job.title, True)
        out.append(job)
    return out


def _ashby(company: str, slug: str) -> list[Job]:
    data = httpx.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                          params={"includeCompensation": "false"})
    jobs = (data or {}).get("jobs") or []
    out = []
    for j in jobs:
        loc = j.get("location") or ""
        job = _mk(company, j.get("title", ""), loc, j.get("jobUrl", ""),
                  _strip_html(j.get("descriptionHtml", "")), "")
        if j.get("isRemote"):
            job.is_remote = True
            job.remote_scope = derive_remote_scope(job.location, job.title, True)
        out.append(job)
    return out


_FETCHERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def fetch_company(company: str, provider: str, slug: str) -> list[Job]:
    fn = _FETCHERS.get(provider)
    return fn(company, slug) if fn else []


def _resolve(entry: str) -> tuple[str, str, str] | None:
    """Turn a config entry into (display_name, provider, slug).

    Accepts a bare name resolved via COMPANY_BOARDS, or an explicit
    'Name|provider|slug' (or 'Name:provider:slug') override.
    """
    sep = "|" if "|" in entry else (":" if entry.count(":") == 2 else None)
    if sep:
        name, provider, slug = (p.strip() for p in entry.split(sep, 2))
        return name, provider.lower(), slug
    known = COMPANY_BOARDS.get(entry.strip().lower())
    if known:
        return entry.strip(), known[0], known[1]
    return None


def _role_keywords(search: dict) -> set[str]:
    kws = {t.lower().strip() for t in (search.get("terms") or []) if t.strip()}
    kws |= {"software engineer", "backend", "product security", "application security",
            "detection engineer", "reverse engineer", "malware", "vulnerability", "exploit",
            "threat", "appsec", "security researcher"}
    return kws


def _target_locations(search: dict) -> set[str]:
    locs = set()
    for prof in (search.get("profiles") or []):
        loc = (prof.get("location") or "").strip().lower()
        if loc and loc != "remote":
            locs.add(loc)
    for key in ("location", "country_indeed"):
        v = (search.get(key) or "").strip().lower()
        if v and v != "remote":
            locs.add(v)
    return locs


def _matches(job: Job, locs: set[str], roles: set[str], want_remote: bool,
             home: str = "India", geo_on: bool = True) -> bool:
    if geo_on:
        loc_ok = geo.in_scope(job, home)
    else:
        loc = (job.location or "").lower()
        loc_ok = (want_remote and job.is_remote) or (not locs) or any(s in loc for s in locs)
    title = (job.title or "").lower()
    role_ok = (not roles) or any(k in title for k in roles)
    return loc_ok and role_ok


def run(cfg: dict, store) -> int:
    """Fetch each configured target company's board, filter, and upsert. Returns new count."""
    s = cfg.get("search", {})
    entries = s.get("companies") or []
    if not entries:
        return 0
    locs = _target_locations(s)
    roles = _role_keywords(s)
    want_remote = bool(s.get("is_remote", True)) or any(
        p.get("is_remote") for p in (s.get("profiles") or []))
    home = s.get("home_country", "India")
    geo_on = bool(s.get("scope_to_home", True))
    print("\n  == ATS boards (direct company fetch) ==")
    new_total = 0
    closed_total = 0
    for entry in entries:
        resolved = _resolve(entry)
        if not resolved:
            print(f"  [{entry}] unknown company (add to companies.COMPANY_BOARDS or use Name|provider|slug)")
            continue
        name, provider, slug = resolved
        try:
            board = fetch_company(name, provider, slug)
        except Exception:  # noqa: BLE001 - best-effort, never break the scan
            board = []
        kept = [j for j in board if _matches(j, locs, roles, want_remote, home, geo_on)]
        new_here = 0
        for job in kept:
            if job.title and job.company and store.upsert_job(job):
                new_here += 1
        new_total += new_here
        # The board is the full source of truth: anything we stored before that
        # is no longer listed has been taken down. Only reconcile on a real fetch
        # (non-empty board) so a transient failure never mass-closes a company.
        closed_here = 0
        if board:
            closed_here = store.reconcile_open("ats", name, {j.url for j in board})
            closed_total += closed_here
        tail = f", {closed_here} taken down" if closed_here else ""
        print(f"  [{name}] {len(board)} on board / {len(kept)} matched ({new_here} new{tail})")
        store.log_run(f"ats:{name}", len(kept), "ok")
    print(f"  ATS complete: {new_total} new, {closed_total} taken down from {len(entries)} companies")
    return new_total
