"""Glassdoor lookup link -- deliberately makes no request.

Glassdoor's terms do not permit automated reads, and their Cloudflare/auth wall
blocks them anyway, so the rating scrape that used to live here failed almost
every time and left ``Rating: null`` in the drawer. What is actually useful is the
link, and that is pure string formatting: no network, no terms problem, no
failure mode.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from .registry import source


@source(section="glassdoor", config_key="glassdoor")
def enrich(company: str) -> dict[str, Any]:
    return {
        "search_url":
            f"https://www.glassdoor.com/Search/results.htm?keyword={quote_plus(company)}",
    }
