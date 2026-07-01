"""Tiny HTTP helper (requests wrapper) with a UA, timeout, and JSON convenience.

Every enricher is best-effort: network failures return None/empty rather than
raising, so one dead source never breaks a run.
"""
from __future__ import annotations

from typing import Any, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 jobscope/0.1"
)
DEFAULT_TIMEOUT = 12


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT):
    import requests
    h = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    return requests.get(url, params=params, headers=h, timeout=timeout)


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT) -> Optional[Any]:
    try:
        resp = get(url, params=params, headers={"Accept": "application/json", **(headers or {})},
                   timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception:  # noqa: BLE001 - best-effort
        return None
    return None


def get_text(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    try:
        resp = get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
    except Exception:  # noqa: BLE001 - best-effort
        return None
    return None
