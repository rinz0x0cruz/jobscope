"""Glassdoor enrichment (best-effort, opt-in).

Glassdoor aggressively blocks automated access (Cloudflare + auth walls), so this
is intentionally conservative: it always returns a search link, and only attempts
a lightweight rating parse. Enable via `enrich.glassdoor: true`.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote_plus

from .. import httpx
from .registry import source


@source(section="glassdoor", config_key="glassdoor")
def enrich(company: str) -> Optional[dict[str, Any]]:
    search_url = f"https://www.glassdoor.com/Search/results.htm?keyword={quote_plus(company)}"
    out: dict[str, Any] = {"search_url": search_url, "rating": None}

    html = httpx.get_text(search_url)
    if html:
        m = re.search(r'"overallRating"\s*:\s*([0-5](?:\.\d)?)', html) or \
            re.search(r'rating[^0-9]{0,12}([0-5]\.\d)\s*(?:out of|/)\s*5', html, re.IGNORECASE)
        if m:
            try:
                out["rating"] = float(m.group(1))
            except ValueError:
                pass
    if out["rating"] is None:
        out["note"] = "open the search link (Glassdoor blocks automated rating reads)"
    return out
