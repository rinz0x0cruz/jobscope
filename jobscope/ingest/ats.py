"""Company-targeted fetching from public ATS job boards.

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
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlparse

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
    "ntt data": ("phenom", "NTT1GLOBAL"),
}


_PHENOM_BOARDS = {
    "ntt1global": {
        "site": "https://careers.services.global.ntt/global/en",
        "category": "Information Security",
    },
}
_PHENOM_HOSTS = {
    "careers.services.global.ntt": "NTT1GLOBAL",
}
_PHENOM_PAGE_SIZE = 50
_PHENOM_MAX_JOBS = 500
_PHENOM_MAX_DETAILS = 25


class BoardStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    PARTIAL = "partial"
    INVALID = "invalid"
    ERROR = "error"
    UNSUPPORTED = "unsupported"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class BoardResolution:
    company: str
    status: ResolutionStatus
    provider: str = ""
    slug: str = ""
    careers_url: str = ""
    detail: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == ResolutionStatus.RESOLVED


@dataclass(slots=True)
class BoardFetchResult:
    company: str
    provider: str
    slug: str
    status: BoardStatus
    jobs: list[Job] = field(default_factory=list)
    detail: str = ""
    attempts: int = 0
    status_code: int | None = None

    @property
    def successful(self) -> bool:
        return self.status in {BoardStatus.OK, BoardStatus.EMPTY, BoardStatus.PARTIAL}


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


def _load_json(url: str, *, params: dict) -> tuple[Any | None, str, int, int | None]:
    result = httpx.get_json_result(url, params=params)
    if not result.ok:
        status = f"HTTP {result.status_code}" if result.status_code is not None else "network error"
        attempt_word = "attempt" if result.attempts == 1 else "attempts"
        detail = result.error or status
        return None, f"{detail} after {result.attempts} {attempt_word}", result.attempts, result.status_code
    return result.data, "", result.attempts, result.status_code


def _finish_result(company: str, provider: str, slug: str, jobs: list[Job],
                   malformed: int = 0, *, attempts: int = 0,
                   status_code: int | None = None) -> BoardFetchResult:
    if malformed:
        status = BoardStatus.PARTIAL if jobs else BoardStatus.INVALID
        detail = f"{malformed} malformed posting(s)"
    else:
        status = BoardStatus.OK if jobs else BoardStatus.EMPTY
        detail = ""
    return BoardFetchResult(
        company, provider, slug, status, jobs, detail, attempts, status_code)


def _greenhouse(company: str, slug: str) -> BoardFetchResult:
    data, error, attempts, status_code = _load_json(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        params={"content": "true"},
    )
    if error:
        return BoardFetchResult(
            company, "greenhouse", slug, BoardStatus.ERROR, detail=error,
            attempts=attempts, status_code=status_code)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return BoardFetchResult(
            company, "greenhouse", slug, BoardStatus.INVALID,
            detail="response does not contain a jobs list", attempts=attempts,
            status_code=status_code,
        )
    out: list[Job] = []
    malformed = 0
    for posting in data["jobs"]:
        try:
            loc = ((posting.get("location") or {}).get("name") or "")
            out.append(_mk(
                company, posting.get("title", ""), loc,
                posting.get("absolute_url", ""),
                _strip_html(posting.get("content", "")),
                str(posting.get("updated_at", "")),
            ))
        except (AttributeError, TypeError, ValueError):
            malformed += 1
    return _finish_result(
        company, "greenhouse", slug, out, malformed,
        attempts=attempts, status_code=status_code)


def _lever(company: str, slug: str) -> BoardFetchResult:
    data, error, attempts, status_code = _load_json(
        f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if error:
        return BoardFetchResult(
            company, "lever", slug, BoardStatus.ERROR, detail=error,
            attempts=attempts, status_code=status_code)
    if not isinstance(data, list):
        return BoardFetchResult(
            company, "lever", slug, BoardStatus.INVALID,
            detail="response is not a postings list", attempts=attempts,
            status_code=status_code,
        )
    out: list[Job] = []
    malformed = 0
    for posting in data:
        try:
            cats = posting.get("categories") or {}
            loc = cats.get("location") or ""
            workplace_type = (posting.get("workplaceType") or "").lower()
            desc = posting.get("descriptionPlain") or _strip_html(
                posting.get("description", ""))
            job = _mk(
                company, posting.get("text", ""), loc,
                posting.get("hostedUrl", ""), desc,
                _ms_to_date(posting.get("createdAt")),
            )
            if workplace_type == "remote":
                job.is_remote = True
                job.remote_scope = derive_remote_scope(job.location, job.title, True)
            out.append(job)
        except (AttributeError, TypeError, ValueError):
            malformed += 1
    return _finish_result(
        company, "lever", slug, out, malformed,
        attempts=attempts, status_code=status_code)


def _ashby(company: str, slug: str) -> BoardFetchResult:
    data, error, attempts, status_code = _load_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        params={"includeCompensation": "false"},
    )
    if error:
        return BoardFetchResult(
            company, "ashby", slug, BoardStatus.ERROR, detail=error,
            attempts=attempts, status_code=status_code)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return BoardFetchResult(
            company, "ashby", slug, BoardStatus.INVALID,
            detail="response does not contain a jobs list", attempts=attempts,
            status_code=status_code,
        )
    out: list[Job] = []
    malformed = 0
    for posting in data["jobs"]:
        try:
            loc = posting.get("location") or ""
            job = _mk(
                company, posting.get("title", ""), loc,
                posting.get("jobUrl", ""),
                _strip_html(posting.get("descriptionHtml", "")), "",
            )
            if posting.get("isRemote"):
                job.is_remote = True
                job.remote_scope = derive_remote_scope(job.location, job.title, True)
            out.append(job)
        except (AttributeError, TypeError, ValueError):
            malformed += 1
    return _finish_result(
        company, "ashby", slug, out, malformed,
        attempts=attempts, status_code=status_code)


def _phenom(company: str, slug: str) -> BoardFetchResult:
    board = _PHENOM_BOARDS.get((slug or "").lower())
    if not board:
        return BoardFetchResult(
            company, "phenom", slug, BoardStatus.UNSUPPORTED,
            detail=f"unknown Phenom tenant: {slug or '<empty>'}",
        )
    endpoint = f"https://content-ir.phenompeople.com/api/{slug}/refineSearch"
    selected_fields = {"category": [board["category"]]} if board.get("category") else {}
    jobs_by_id: dict[str, Job] = {}
    malformed = 0
    attempts = 0
    status_code: int | None = None
    total_hits: int | None = None
    for start in range(0, _PHENOM_MAX_JOBS, _PHENOM_PAGE_SIZE):
        payload = {
            "ddoKey": "refineSearch",
            "from": start,
            "size": _PHENOM_PAGE_SIZE,
            "global": True,
            "keywords": "",
            "all_fields": ["city", "state", "category", "type", "orgFunction", "country"],
            "selected_fields": selected_fields,
            "sortBy": "",
            "subsearch": "",
            "jdsource": "facets",
            "siteType": "external",
            "forceSpellCheck": True,
            "jobs": True,
            "counts": True,
            "isSliderEnable": False,
        }
        data, error, page_attempts, page_status = _load_json(
            endpoint,
            params={
                "locale": "en_global",
                "siteType": "external",
                "deviceType": "desktop",
                "payload": json.dumps(payload, separators=(",", ":")),
            },
        )
        attempts += page_attempts
        status_code = page_status
        if error:
            status = BoardStatus.PARTIAL if jobs_by_id else BoardStatus.ERROR
            return BoardFetchResult(
                company, "phenom", slug, status, list(jobs_by_id.values()), error,
                attempts, status_code,
            )
        search = data.get("refineSearch") if isinstance(data, dict) else None
        rows = ((search.get("data") or {}).get("jobs") if isinstance(search, dict) else None)
        if not isinstance(rows, list):
            return BoardFetchResult(
                company, "phenom", slug,
                BoardStatus.PARTIAL if jobs_by_id else BoardStatus.INVALID,
                list(jobs_by_id.values()), "response does not contain a jobs list",
                attempts, status_code,
            )
        try:
            total_hits = int(search.get("totalHits") or 0)
        except (TypeError, ValueError):
            total_hits = None
        for posting in rows:
            try:
                job_id = str(posting.get("jobId") or posting.get("reqId") or "").strip()
                title = str(posting.get("title") or "").strip()
                if not job_id or not title:
                    raise ValueError("job id and title required")
                locations = posting.get("multi_location") or []
                location = " | ".join(str(item).strip() for item in locations if str(item).strip())
                location = location or str(posting.get("location") or "").strip()
                parser = posting.get("ml_job_parser") or {}
                description = (
                    parser.get("descriptionTeaser_ats")
                    or parser.get("descriptionTeaser_keyword")
                    or posting.get("descriptionTeaser")
                    or ""
                )
                url_title = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
                job = _mk(
                    company, title, location,
                    f"{board['site']}/job/{job_id}/{url_title}",
                    str(description), str(posting.get("postedDate") or ""),
                )
                jobs_by_id[job_id] = job
            except (AttributeError, TypeError, ValueError):
                malformed += 1
        if not rows or total_hits is None or len(jobs_by_id) >= total_hits:
            break
    jobs = list(jobs_by_id.values())
    expected = min(total_hits or len(jobs), _PHENOM_MAX_JOBS)
    if len(jobs) < expected:
        return BoardFetchResult(
            company, "phenom", slug, BoardStatus.PARTIAL, jobs,
            f"received {len(jobs)} of {expected} expected jobs",
            attempts, status_code,
        )
    if total_hits is not None and total_hits > _PHENOM_MAX_JOBS:
        return BoardFetchResult(
            company, "phenom", slug, BoardStatus.PARTIAL, jobs,
            f"board has {total_hits} jobs; capped at {_PHENOM_MAX_JOBS}",
            attempts, status_code,
        )
    return _finish_result(
        company, "phenom", slug, jobs, malformed,
        attempts=attempts, status_code=status_code,
    )


_FETCHERS = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "ashby": _ashby,
    "phenom": _phenom,
}
SUPPORTED_PROVIDERS = frozenset(_FETCHERS)


def fetch_company_result(company: str, provider: str, slug: str) -> BoardFetchResult:
    provider = (provider or "").lower().strip()
    fn = _FETCHERS.get(provider)
    if fn is None:
        return BoardFetchResult(
            company, provider, slug, BoardStatus.UNSUPPORTED,
            detail=f"unsupported ATS provider: {provider or '<empty>'}",
        )
    return fn(company, slug)


def fetch_company(company: str, provider: str, slug: str) -> list[Job]:
    """Compatibility wrapper returning only parsed jobs.

    New orchestration code should use :func:`fetch_company_result` so a valid
    empty board is not confused with a failed request.
    """
    return fetch_company_result(company, provider, slug).jobs


def resolve_config_entry(entry: str) -> tuple[str, str, str] | None:
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


def _resolve(entry: str) -> tuple[str, str, str] | None:
    """Backward-compatible alias for the public offline config resolver."""
    return resolve_config_entry(entry)


_PROBE_ORDER = ("greenhouse", "lever", "ashby")

_UNSUPPORTED_ATS_HOSTS = (
    "myworkdayjobs.com", "workday.com", "icims.com", "smartrecruiters.com",
)


def board_url(provider: str, slug: str) -> str:
    templates = {
        "greenhouse": "https://boards.greenhouse.io/{slug}",
        "lever": "https://jobs.lever.co/{slug}",
        "ashby": "https://jobs.ashbyhq.com/{slug}",
    }
    if (provider == "phenom"):
        board = _PHENOM_BOARDS.get((slug or "").lower())
        return f"{board['site']}/search-results" if board else ""
    template = templates.get((provider or "").lower())
    return template.format(slug=slug) if template and slug else ""


def parse_board_url(url: str) -> tuple[str, str] | None:
    """Extract a supported provider + board slug from a careers/posting URL."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        return "greenhouse", parts[0]
    if host == "boards-api.greenhouse.io" and len(parts) >= 3 and parts[:2] == ["v1", "boards"]:
        return "greenhouse", parts[2]
    if host == "jobs.lever.co" and parts:
        return "lever", parts[0]
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", parts[0]
    if host in _PHENOM_HOSTS:
        return "phenom", _PHENOM_HOSTS[host]
    return None


def _unsupported_ats_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _UNSUPPORTED_ATS_HOSTS)


def _board_from_careers_page(url: str) -> tuple[str, str] | None:
    result = httpx.get_text_result(url)
    if not result.ok or not isinstance(result.data, str):
        return None
    candidates = re.findall(r"(?is)href\s*=\s*['\"]([^'\"]+)['\"]", result.data)
    candidates += re.findall(r"https?://[^\s'\"<>]+", result.data)
    for candidate in candidates:
        parsed = parse_board_url(urljoin(url, _html.unescape(candidate)))
        if parsed:
            return parsed
    return None


def _slug_variants(name: str) -> list[str]:
    """Plausible board slugs for a company name, most-likely first."""
    low = (name or "").lower()
    parts = low.split()
    compact = re.sub(r"[^a-z0-9]+", "", low)
    hyphen = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    first = re.sub(r"[^a-z0-9]", "", parts[0]) if parts else ""
    out: list[str] = []
    for s in (compact, hyphen, first):
        if s and s not in out:
            out.append(s)
    return out


def resolve_board_result(name: str, *, provider: str | None = None,
                         slug: str | None = None, careers_url: str = "",
                         probe: bool = True,
                         inspect_careers_page: bool = True) -> BoardResolution:
    """Resolve a company and optional careers URL to a typed board outcome.

    Priority: an explicit ``provider`` + ``slug`` -> a ``Name|provider|slug`` override
    embedded in ``name`` or the curated :data:`COMPANY_BOARDS` map (both via
    :func:`resolve_config_entry`) -> a supported ATS URL (or link on an official
    careers page) -> an optional best-effort board probe.
    """
    display = (name or "").strip()
    if not display:
        return BoardResolution(display, ResolutionStatus.UNRESOLVED, detail="company is required")
    if provider and slug:
        normalized_provider = provider.lower().strip()
        normalized_slug = slug.strip()
        if normalized_provider not in SUPPORTED_PROVIDERS:
            return BoardResolution(
                display, ResolutionStatus.UNSUPPORTED, normalized_provider, normalized_slug,
                careers_url, f"unsupported ATS provider: {normalized_provider}",
            )
        return BoardResolution(
            display, ResolutionStatus.RESOLVED, normalized_provider, normalized_slug,
            board_url(normalized_provider, normalized_slug),
        )
    embedded = resolve_config_entry(display)
    if embedded:
        company, embedded_provider, embedded_slug = embedded
        if embedded_provider not in SUPPORTED_PROVIDERS:
            return BoardResolution(
                company, ResolutionStatus.UNSUPPORTED, embedded_provider, embedded_slug,
                careers_url, f"unsupported ATS provider: {embedded_provider}",
            )
        return BoardResolution(
            company, ResolutionStatus.RESOLVED, embedded_provider, embedded_slug,
            board_url(embedded_provider, embedded_slug),
        )
    if careers_url:
        direct = parse_board_url(careers_url)
        discovered = direct or (
            _board_from_careers_page(careers_url) if inspect_careers_page else None
        )
        if discovered:
            discovered_provider, discovered_slug = discovered
            return BoardResolution(
                display, ResolutionStatus.RESOLVED, discovered_provider, discovered_slug,
                board_url(discovered_provider, discovered_slug),
            )
        if _unsupported_ats_url(careers_url):
            return BoardResolution(
                display, ResolutionStatus.UNSUPPORTED, careers_url=careers_url,
                detail="career portal uses an unsupported ATS",
            )
    if not probe:
        return BoardResolution(
            display, ResolutionStatus.UNRESOLVED, careers_url=careers_url,
            detail="no supported ATS board resolved",
        )
    for slug_guess in _slug_variants(display):
        for prov in _PROBE_ORDER:
            result = fetch_company_result(display, prov, slug_guess)
            if result.successful and result.jobs:
                return BoardResolution(
                    display, ResolutionStatus.RESOLVED, prov, slug_guess,
                    board_url(prov, slug_guess),
                )
    return BoardResolution(
        display, ResolutionStatus.UNRESOLVED, careers_url=careers_url,
        detail="no public Greenhouse, Lever, Ashby, or curated Phenom board found",
    )


def resolve_board(name: str, *, provider: str | None = None,
                  slug: str | None = None) -> tuple[str, str, str] | None:
    """Compatibility wrapper returning the historical tuple-or-None shape."""
    resolution = resolve_board_result(name, provider=provider, slug=slug)
    if not resolution.resolved:
        return None
    return resolution.company, resolution.provider, resolution.slug


def _role_keywords(search: dict) -> set[str]:
    kws = {t.lower().strip() for t in (search.get("terms") or []) if t.strip()}
    kws |= {"threat hunter", "product security", "application security",
            "detection engineer", "reverse engineer", "malware", "vulnerability", "exploit",
            "threat", "appsec", "security researcher", "soc", "information security",
            "security analyst", "incident response", "penetration tester", "red team", "siem"}
    return kws


def _title_has_role(title: str, role: str) -> bool:
    normalized_title = re.sub(r"[^a-z0-9+#]+", " ", title.lower()).strip()
    normalized_role = re.sub(r"[^a-z0-9+#]+", " ", role.lower()).strip()
    if not normalized_role:
        return False
    return bool(re.search(
        r"(?<![a-z0-9])" + re.escape(normalized_role) + r"(?![a-z0-9])",
        normalized_title,
    ))


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
    return (
        _location_matches(job, locs, want_remote, home, geo_on)
        and _role_matches(job, roles)
    )


def _location_matches(job: Job, locs: set[str], want_remote: bool,
                      home: str = "India", geo_on: bool = True) -> bool:
    if geo_on:
        return geo.in_scope(job, home)
    loc = (job.location or "").lower()
    return (want_remote and job.is_remote) or (not locs) or any(s in loc for s in locs)


def _role_matches(job: Job, roles: set[str]) -> bool:
    title = (job.title or "").lower()
    return (not roles) or any(_title_has_role(title, role) for role in roles)


def filter_board_jobs(cfg: dict, jobs: list[Job]) -> list[Job]:
    """Apply the configured role/location/geo prefilter to one ATS board."""
    search = cfg.get("search", {}) or {}
    locs = _target_locations(search)
    roles = _role_keywords(search)
    want_remote = bool(search.get("is_remote", True)) or any(
        profile.get("is_remote") for profile in (search.get("profiles") or []))
    home = search.get("home_country", "India")
    geo_on = bool(search.get("scope_to_home", True))
    return [job for job in jobs if _matches(job, locs, roles, want_remote, home, geo_on)]


def filter_profile_jobs(cfg: dict, store, jobs: list[Job]) -> list[Job]:
    """Apply active profile fetch intent before the standard board filter."""
    candidates, _ = filter_profile_jobs_with_funnel(cfg, store, jobs)
    return candidates


def filter_profile_jobs_with_funnel(
    cfg: dict, store, jobs: list[Job],
) -> tuple[list[Job], dict[str, Any]]:
    """Return active-profile candidates plus observable geo/title stage counts."""
    from jobscope.analyze import profile

    current = profile.load(cfg)
    search = cfg.get("search", {}) or {}
    if current:
        search = profile.apply_to_search(search, current)
    locs = _target_locations(search)
    roles = _role_keywords(search)
    want_remote = bool(search.get("is_remote", True)) or any(
        item.get("is_remote") for item in (search.get("profiles") or [])
    )
    home = search.get("home_country", "India")
    geo_on = bool(search.get("scope_to_home", True))
    geo_jobs = [
        job for job in jobs
        if _location_matches(job, locs, want_remote, home, geo_on)
    ]
    candidates = [job for job in geo_jobs if _role_matches(job, roles)]
    return candidates, {
        "board": len(jobs),
        "geo_eligible": len(geo_jobs),
        "title_eligible": len(candidates),
    }


def hydrate_company_jobs(
    provider: str, jobs: list[Job], *, stats: dict[str, int] | None = None,
) -> list[Job]:
    """Best-effort detail hydration after geo/title filtering has bounded the set."""
    if stats is not None:
        stats.update(attempted=0, hydrated=0, failed=0)
    if (provider or "").lower() != "phenom":
        return jobs
    marker = "phApp.ddo = "
    for job in jobs[:_PHENOM_MAX_DETAILS]:
        if stats is not None:
            stats["attempted"] += 1
        result = httpx.get_text_result(job.url)
        if not result.ok or not isinstance(result.data, str):
            if stats is not None:
                stats["failed"] += 1
            continue
        start = result.data.find(marker)
        if start < 0:
            if stats is not None:
                stats["failed"] += 1
            continue
        try:
            payload, _ = json.JSONDecoder().raw_decode(result.data[start + len(marker):])
            detail = payload["jobDetail"]["data"]["job"]
            description = _strip_html(detail.get("description") or "")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            if stats is not None:
                stats["failed"] += 1
            continue
        if description:
            job.description = description
            if stats is not None:
                stats["hydrated"] += 1
        elif stats is not None:
            stats["failed"] += 1
    return jobs


def run(cfg: dict, store) -> int:
    """Fetch each configured target company's board, filter, and upsert. Returns new count."""
    s = cfg.get("search", {})
    entries = s.get("companies") or []
    if not entries:
        return 0
    print("\n  == ATS boards (direct company fetch) ==")
    new_total = 0
    closed_total = 0
    for entry in entries:
        resolved = _resolve(entry)
        if not resolved:
            print(f"  [{entry}] unknown company (add to companies.COMPANY_BOARDS or use Name|provider|slug)")
            store.log_run(f"ats:{entry}", 0, BoardStatus.UNSUPPORTED.value)
            continue
        name, provider, slug = resolved
        result = fetch_company_result(name, provider, slug)
        board = result.jobs
        store.set_source_health(
            f"ats:{name}", provider=provider, slug=slug,
            status=result.status.value, item_count=len(board),
            attempts=result.attempts, status_code=result.status_code,
            detail=result.detail,
        )
        if not result.successful:
            print(f"  [{name}] {result.status.value}: {result.detail}")
            store.log_run(f"ats:{name}", 0, result.status.value)
            continue
        kept = filter_profile_jobs(cfg, store, board)
        kept = hydrate_company_jobs(provider, kept)
        new_here = 0
        for job in kept:
            if job.title and job.company and store.upsert_job(job):
                new_here += 1
        new_total += new_here
        # Only a complete, non-empty board is authoritative enough to close jobs.
        # Empty and partial results remain observable but deliberately non-destructive.
        closed_here = 0
        if result.status == BoardStatus.OK and board:
            closed_here = store.reconcile_open("ats", name, {j.url for j in board})
            closed_total += closed_here
        tail = f", {closed_here} taken down" if closed_here else ""
        health = f", {result.status.value}: {result.detail}" if result.detail else ""
        print(f"  [{name}] {len(board)} on board / {len(kept)} matched "
              f"({new_here} new{tail}{health})")
        store.log_run(f"ats:{name}", len(kept), result.status.value)
    print(f"  ATS complete: {new_total} new, {closed_total} taken down from {len(entries)} companies")
    return new_total
