"""Deterministic, evidence-backed company ranking for outreach campaigns."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Iterable, Optional

from jobscope.core.companies import SECURITY, company_funding, company_quality, company_size
from jobscope.core.geo import in_scope, is_home_location
from jobscope.core.store.monitoring import normalize_company_key
from jobscope.core.store.outreach_campaigns import MAX_CAMPAIGN_TARGETS

DEFAULT_WEIGHTS = {"region": 0.5, "compensation": 0.3, "growth": 0.2}
MIN_REGION_SCORE = 0.6

# Employers with recurring India security hiring or established India operations.
# The baseline is deliberately modest; live Jobscope evidence can raise it.
INDIA_CYBERSECURITY_POOL = (
    "Akamai", "Check Point", "Cisco", "CrowdStrike", "CyberArk", "Fortinet",
    "Google", "Microsoft", "Netskope", "Palo Alto Networks", "Qualys",
    "Securonix", "SentinelOne", "Sophos", "Trellix", "Zscaler",
)

_EXPLICIT_SECURITY_TITLE_TERMS = (
    "application security", "appsec", "blue team", "cloud security", "computer forensic",
    "cyber", "cybersecurity", "data security", "devsecops", "dfir", "digital forensic",
    "endpoint security", "grc", "iam", "identity and access", "incident response",
    "information security", "infosec", "malware", "network security",
    "offensive security", "penetration", "product security", "red team", "secops",
    "security operations", "security program", "soc analyst", "soc manager",
    "software supply chain security", "threat", "vulnerabilities", "vulnerability",
)
_SECURITY_ROLE_NOUNS = frozenset({
    "administrator", "advisor", "analyst", "architect", "auditor", "consultant",
    "director", "engineer", "intern", "lead", "manager", "researcher", "specialist",
})
_PHYSICAL_SECURITY_TITLE_TERMS = (
    "armed guard", "loss prevention", "physical security", "security guard",
    "security officer", "security personnel", "security supervisor", "unarmed guard",
)
_GROWTH_POSITIVE = (
    "expands", "expansion", "funding", "growth", "hires", "hiring", "opens",
    "raises", "series ", "new office", "adds jobs",
)
_GROWTH_NEGATIVE = (
    "bankruptcy", "closes office", "cuts jobs", "downsizes", "layoff", "layoffs",
    "restructuring",
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _campaign_config(cfg: dict) -> dict:
    outreach = (cfg.get("apply", {}).get("outreach", {}) or {})
    return outreach.get("campaign", {}) or {}


def _weights(raw: Optional[dict]) -> dict[str, float]:
    values = dict(DEFAULT_WEIGHTS if raw is None else raw)
    if set(values) != set(DEFAULT_WEIGHTS):
        raise ValueError("campaign weights must contain region, compensation, and growth")
    parsed = {key: float(value) for key, value in values.items()}
    if any(value < 0 for value in parsed.values()) or not math.isclose(
        sum(parsed.values()), 1.0, abs_tol=1e-6,
    ):
        raise ValueError("campaign weights must be non-negative and sum to 1")
    return parsed


def _parse_time(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days(job, now: datetime) -> Optional[int]:
    seen = _parse_time(job.date_posted) or _parse_time(job.last_seen)
    if seen is None:
        return None
    return max(0, (now - seen).days)


def is_security_role(job) -> bool:
    """Whether a posting is explicitly security-focused and profile-relevant.

    Company boilerplate and descriptions often mention security even for backend,
    sales, or product roles. Campaigns therefore require a title signal and reject
    roles the active profile already scored as Skip.
    """
    if str(job.tier or "").strip().casefold() == "skip":
        return False
    title = " ".join(str(job.title or "").casefold().replace("/", " ").split())
    padded = f" {title} "
    if any(term in title for term in _PHYSICAL_SECURITY_TITLE_TERMS):
        return False
    if any(f" {term} " in padded for term in _EXPLICIT_SECURITY_TITLE_TERMS):
        return True
    tokens = title.split()
    for index, token in enumerate(tokens):
        if token != "security":
            continue
        previous = tokens[index - 1] if index else ""
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if previous in _SECURITY_ROLE_NOUNS or following in _SECURITY_ROLE_NOUNS:
            return True
    return False


def _pool_entry(pool: dict[str, dict], company: str, source: str, *,
                curated_relevance: float = 0) -> None:
    display = (company or "").strip()
    key = normalize_company_key(display)
    if not key:
        return
    entry = pool.setdefault(key, {
        "company": display,
        "company_key": key,
        "sources": [],
        "curated_relevance": 0.0,
    })
    if source not in entry["sources"]:
        entry["sources"].append(source)
    entry["curated_relevance"] = max(entry["curated_relevance"], curated_relevance)


def _company_overrides(campaign_cfg: dict) -> dict[str, dict]:
    overrides: dict[str, dict] = {}
    for company, raw in (campaign_cfg.get("company_overrides") or {}).items():
        key = normalize_company_key(company)
        if key and isinstance(raw, dict):
            overrides[key] = dict(raw)
    return overrides


def _candidate_pool(cfg: dict, store, candidates: Optional[Iterable[str]]) -> dict[str, dict]:
    pool: dict[str, dict] = {}
    campaign_cfg = _campaign_config(cfg)
    if candidates is not None:
        for company in candidates:
            _pool_entry(pool, company, "explicit")
        return pool

    for monitor in store.list_company_monitors():
        _pool_entry(pool, monitor.get("company") or "", "watching")
    for job in store.jobs(order_by_score=False):
        _pool_entry(pool, job.company, "collected")
    for company in SECURITY:
        _pool_entry(pool, company, "security_registry")
    if campaign_cfg.get("include_default_pool", True):
        for company in INDIA_CYBERSECURITY_POOL:
            _pool_entry(pool, company, "india_security_curated", curated_relevance=0.65)

    for raw in campaign_cfg.get("curated_companies") or []:
        if isinstance(raw, str):
            _pool_entry(pool, raw, "user_curated", curated_relevance=0.65)
            continue
        if isinstance(raw, dict):
            company = raw.get("name") or raw.get("company") or ""
            relevance = _clamp(raw.get("india_relevance", 0.65))
            _pool_entry(pool, company, "user_curated", curated_relevance=relevance)
    return pool


def _application_history(store) -> dict[str, dict]:
    history: dict[str, dict] = {}
    for application in store.applications(include_tombstoned=True):
        company = (application.get("company") or "").strip()
        key = normalize_company_key(company)
        if key and key not in history:
            history[key] = {
                "company": company,
                "company_key": key,
                "status": application.get("status") or "",
                "job_id": application.get("job_id") or "",
                "updated": application.get("updated") or "",
            }
    return history


def _region_factor(jobs: list, entry: dict, override: dict,
                   now: datetime) -> tuple[float, float, list[str]]:
    if "india_relevance" in override:
        score = _clamp(override["india_relevance"])
        note = override.get("india_evidence") or "User-supplied India relevance override"
        return score, 1.0, [str(note)]

    score = float(entry.get("curated_relevance") or 0)
    evidence = (["Included in the curated India-relevant cybersecurity pool"] if score else [])
    matching = 0
    for job in jobs:
        if not is_security_role(job):
            continue
        if (job.status or "open") == "closed":
            continue
        age = _age_days(job, now)
        if age is not None and age > 365:
            continue
        signal = 0.0
        if is_home_location(job, "India"):
            signal = 1.0
        elif job.is_remote and in_scope(job, "India"):
            scope = (job.remote_scope or "global").strip().lower()
            if scope == "india":
                signal = 1.0
            elif scope in {"apac", "asia", "asia pacific", "asia-pacific", "south asia"}:
                signal = 0.85
            elif scope in {"", "global", "worldwide", "anywhere"}:
                signal = 0.7
        if not signal:
            continue
        if age is not None and age > 180:
            signal *= 0.85
        matching += 1
        score = max(score, signal)
        evidence.append(f"{job.title} — {job.location or job.remote_scope or 'remote'}")
    if matching >= 3:
        score = min(1.0, score + 0.05)
    coverage = 1.0 if matching else (0.65 if score else 0.0)
    return _clamp(score), coverage, evidence[:5]


def _annual_salary(job) -> Optional[tuple[str, float]]:
    value = job.salary_max or job.salary_min
    if not value or value <= 0:
        return None
    interval = (job.salary_interval or "yearly").strip().lower()
    multiplier = 1.0
    if interval in {"month", "monthly"}:
        multiplier = 12.0
    elif interval in {"hour", "hourly"}:
        multiplier = 2080.0
    elif interval not in {"year", "yearly", "annual", "annually", ""}:
        return None
    currency = (job.currency or "unknown").strip().upper()
    return currency, float(value) * multiplier


def _salary_sample(jobs: list) -> Optional[tuple[str, float]]:
    by_currency: dict[str, list[float]] = defaultdict(list)
    for job in jobs:
        salary = _annual_salary(job)
        if salary:
            by_currency[salary[0]].append(salary[1])
    if not by_currency:
        return None
    currency, values = max(by_currency.items(), key=lambda item: (len(item[1]), item[0]))
    return currency, median(values)


def _percentile(value: float, peers: list[float]) -> float:
    ordered = sorted(peers)
    if len(ordered) < 2:
        return 0.75
    below = sum(peer < value for peer in ordered)
    equal = sum(peer == value for peer in ordered)
    rank = below + (equal - 1) / 2
    return 0.35 + 0.65 * rank / (len(ordered) - 1)


def _compensation_factor(company: str, salary: Optional[tuple[str, float]],
                         salary_groups: dict[str, list[float]], override: dict,
                         ) -> tuple[float, float, list[str], str]:
    if "compensation" in override:
        note = override.get("compensation_evidence") or "User-supplied compensation override"
        return _clamp(override["compensation"]), 1.0, [str(note)], "override"
    if salary:
        currency, annual = salary
        score = _percentile(annual, salary_groups[currency])
        return _clamp(score), 1.0, [f"Median structured maximum: {annual:,.0f} {currency}/year"], "structured"

    quality, quality_tier = company_quality(company)
    size, size_tier = company_size(company)
    funding = company_funding(company)
    funding_score = 0.9 if funding == "public" else 0.85 if funding == "unicorn" else 0.5
    score = 0.45 * quality + 0.25 * size + 0.30 * funding_score
    details = [
        "No comparable structured salary; using lower-confidence company proxies",
        f"quality={quality_tier or 'unknown'}, size={size_tier or 'unknown'}, funding={funding or 'unknown'}",
    ]
    return _clamp(score), 0.35, details, "proxy"


def _news_titles(enrichment: dict) -> list[str]:
    raw = enrichment.get("news") or []
    if isinstance(raw, dict):
        raw = raw.get("articles") or raw.get("items") or []
    if not isinstance(raw, list):
        return []
    return [str(item.get("title") or "") for item in raw if isinstance(item, dict)]


def _growth_factor(company: str, jobs: list, enrichment: dict, override: dict,
                   now: datetime) -> tuple[float, float, list[str]]:
    if "growth" in override:
        note = override.get("growth_evidence") or "User-supplied growth override"
        return _clamp(override["growth"]), 1.0, [str(note)]

    recent = prior = 0
    for job in jobs:
        if not is_security_role(job):
            continue
        age = _age_days(job, now)
        if age is None or age <= 90:
            recent += 1
        elif age <= 180:
            prior += 1

    parts: list[tuple[float, float]] = []
    evidence: list[str] = []
    if recent or prior:
        if recent > prior:
            hiring = min(1.0, 0.65 + 0.08 * recent)
        elif recent == prior:
            hiring = 0.6
        else:
            hiring = 0.4
        parts.append((0.6, hiring))
        evidence.append(f"Security hiring: {recent} recent role(s), {prior} in the prior window")

    titles = _news_titles(enrichment)
    positive = sum(any(term in title.lower() for term in _GROWTH_POSITIVE) for title in titles)
    negative = sum(any(term in title.lower() for term in _GROWTH_NEGATIVE) for title in titles)
    if positive or negative:
        news_score = _clamp(0.5 + 0.15 * positive - 0.2 * negative)
        parts.append((0.25, news_score))
        evidence.append(f"Growth news: {positive} positive, {negative} negative signal(s)")

    funding = company_funding(company)
    if funding:
        parts.append((0.15, 0.85 if funding == "unicorn" else 0.8))
        evidence.append(f"Funding tier: {funding}")

    if not parts:
        return 0.5, 0.0, ["No current hiring, funding, or growth-news evidence"]
    available = sum(weight for weight, _ in parts)
    score = sum(weight * value for weight, value in parts) / available
    return _clamp(score), available, evidence


def rank_companies(
    cfg: dict,
    store,
    requested_count: int,
    *,
    candidates: Optional[Iterable[str]] = None,
    weights: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Return the top unique cold-outreach companies plus excluded follow-ups.

    Ranking is offline and side-effect free. Every company with any application
    row is excluded from cold outreach, regardless of current application state.
    """
    if not 1 <= requested_count <= MAX_CAMPAIGN_TARGETS:
        raise ValueError(
            f"requested_count must be between 1 and {MAX_CAMPAIGN_TARGETS}"
        )
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    chosen_weights = _weights(weights or _campaign_config(cfg).get("weights"))
    pool = _candidate_pool(cfg, store, candidates)
    history = _application_history(store)
    campaign_cfg = _campaign_config(cfg)
    overrides = _company_overrides(campaign_cfg)
    do_not_contact = {
        normalize_company_key(value) for value in
        (cfg.get("apply", {}).get("outreach", {}).get("do_not_contact") or [])
        if isinstance(value, str) and normalize_company_key(value)
    }

    jobs_by_company: dict[str, list] = defaultdict(list)
    for job in store.jobs(order_by_score=False):
        key = normalize_company_key(job.company)
        if key:
            jobs_by_company[key].append(job)
    security_jobs_by_company = {
        key: [job for job in jobs if is_security_role(job)]
        for key, jobs in jobs_by_company.items()
    }

    follow_up = [history[key] for key in sorted(pool.keys() & history.keys())]
    blocked: list[dict] = []
    eligible_entries: list[dict] = []
    for key, entry in pool.items():
        if key in history:
            continue
        if key in do_not_contact:
            blocked.append({"company": entry["company"], "company_key": key,
                            "reason": "do_not_contact"})
            continue
        region, region_coverage, region_evidence = _region_factor(
            security_jobs_by_company.get(key, []), entry, overrides.get(key, {}), now,
        )
        if region < MIN_REGION_SCORE:
            blocked.append({"company": entry["company"], "company_key": key,
                            "reason": "insufficient_india_evidence",
                            "region_score": round(region, 4)})
            continue
        eligible_entries.append({
            **entry,
            "region_score": region,
            "region_coverage": region_coverage,
            "region_evidence": region_evidence,
        })

    salaries = {
        entry["company_key"]: _salary_sample(
            security_jobs_by_company.get(entry["company_key"], [])
        )
        for entry in eligible_entries
    }
    salary_groups: dict[str, list[float]] = defaultdict(list)
    for salary in salaries.values():
        if salary:
            salary_groups[salary[0]].append(salary[1])

    ranked: list[dict] = []
    for entry in eligible_entries:
        key = entry["company_key"]
        company = entry["company"]
        override = overrides.get(key, {})
        comp, comp_coverage, comp_evidence, comp_basis = _compensation_factor(
            company, salaries[key], salary_groups, override,
        )
        growth, growth_coverage, growth_evidence = _growth_factor(
            company, security_jobs_by_company.get(key, []),
            store.get_enrichment(company), override, now,
        )
        factor_score = (
            chosen_weights["region"] * entry["region_score"]
            + chosen_weights["compensation"] * comp
            + chosen_weights["growth"] * growth
        )
        coverage = (
            chosen_weights["region"] * entry["region_coverage"]
            + chosen_weights["compensation"] * comp_coverage
            + chosen_weights["growth"] * growth_coverage
        )
        score = _clamp(factor_score - 0.1 * (1 - coverage)) * 100
        ranked.append({
            "company": company,
            "company_key": key,
            "score": round(score, 2),
            "factors": {
                "region": round(entry["region_score"], 4),
                "compensation": round(comp, 4),
                "growth": round(growth, 4),
            },
            "evidence_coverage": round(coverage, 4),
            "evidence": {
                "region": entry["region_evidence"],
                "compensation": comp_evidence,
                "growth": growth_evidence,
                "compensation_basis": comp_basis,
            },
            "sources": entry["sources"],
        })

    ranked.sort(key=lambda item: (-item["score"], item["company"].casefold()))
    blocked.sort(key=lambda item: (item["reason"], item["company"].casefold()))
    return {
        "requested_count": requested_count,
        "eligible_count": len(ranked),
        "ranked": ranked[:requested_count],
        "follow_up": follow_up,
        "blocked": blocked,
        "weights": chosen_weights,
    }