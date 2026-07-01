"""Compensation enrichment.

Primary signal is the posting's own salary (JobSpy parses this for many boards).
We also hand back a Levels.fyi search link for deeper, crowd-sourced numbers.
Kept deterministic and honest -- no fragile scraping by default.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote_plus


def enrich(company: str, job) -> Optional[dict[str, Any]]:
    out: dict[str, Any] = {
        "levels_fyi": f"https://www.levels.fyi/companies/{_slug(company)}/salaries",
        "levels_search": f"https://www.levels.fyi/?search={quote_plus(company)}",
    }
    lo, hi = job.salary_min, job.salary_max
    if lo or hi:
        out.update({
            "min": lo,
            "max": hi,
            "interval": job.salary_interval or "yearly",
            "currency": job.currency or "USD",
            "source": "posting",
            "range": _fmt(lo, hi, job.currency, job.salary_interval),
        })
    return out


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
