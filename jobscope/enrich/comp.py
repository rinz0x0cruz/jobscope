"""Compensation enrichment.

Company enrichment stores Levels.fyi lookup links. A posting's own salary is
kept separately as per-job analysis so one role can never contaminate another
role at the same company. Kept deterministic and honest -- no fragile scraping.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote_plus

from .registry import source


@source(section="comp", config_key="compensation",
        call=lambda fn, ctx: fn(ctx.company, ctx.job))
def enrich(company: str, job) -> Optional[dict[str, Any]]:
    return {
        "levels_fyi": f"https://www.levels.fyi/companies/{_slug(company)}/salaries",
        "levels_search": f"https://www.levels.fyi/?search={quote_plus(company)}",
    }


def posting(job) -> dict[str, Any]:
    """Return compensation stated by this exact posting, with provenance."""
    lo, hi = job.salary_min, job.salary_max
    if not (lo or hi):
        return {}
    return {
        "min": lo,
        "max": hi,
        "interval": job.salary_interval or "yearly",
        "currency": job.currency or "USD",
        "source": "posting",
        "source_url": job.url or "",
        "range": _fmt(lo, hi, job.currency, job.salary_interval),
    }


def _fmt(lo: Optional[float], hi: Optional[float], currency: str, interval: str) -> str:
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get((currency or "").upper(), "")
    unit = f"/{interval}" if interval else ""

    def h(v):
        if not v:
            return ""
        if v >= 1000:
            return f"{sym}{v/1000:.0f}k"
        return f"{sym}{v:.0f}"

    if lo and hi:
        return f"{h(lo)}–{h(hi)}{unit}"
    return f"{h(lo or hi)}{unit}"


def _slug(company: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (company or "").lower()).strip("-")
