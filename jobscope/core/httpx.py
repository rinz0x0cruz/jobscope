"""HTTP helpers with bounded retries and best-effort compatibility wrappers.

Every enricher is best-effort: network failures return None/empty rather than
raising, so one dead source never breaks a run. Callers that need source-health
detail can use the ``*_result`` variants.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 jobscope/0.1"
)
DEFAULT_TIMEOUT = 12
DEFAULT_ATTEMPTS = 3
MAX_RETRY_DELAY = 5.0
RETRYABLE_STATUS_CODES = frozenset({408, 429})


@dataclass(frozen=True, slots=True)
class HttpResult:
    ok: bool
    status_code: int | None
    attempts: int
    data: Any = None
    error: str = ""


def _retry_delay(response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "") if response is not None else ""
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = 0.0
        if delay > 0:
            return min(delay, MAX_RETRY_DELAY)
    return min(0.5 * (2 ** (attempt - 1)), MAX_RETRY_DELAY)


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT):
    import requests
    h = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    return requests.get(url, params=params, headers=h, timeout=timeout)


def _get_result(url: str, *, params: dict | None, headers: dict | None,
                timeout: int, attempts: int, decode: Callable[[Any], Any],
                sleep: Callable[[float], None]) -> HttpResult:
    import requests

    attempts = max(1, attempts)
    request_headers = headers or {}
    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = get(url, params=params, headers=request_headers, timeout=timeout)
        except requests.RequestException as exc:
            if attempt < attempts:
                sleep(_retry_delay(None, attempt))
                continue
            return HttpResult(False, None, attempt, error=f"{type(exc).__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - compatibility: helpers stay best-effort
            return HttpResult(False, None, attempt, error=f"{type(exc).__name__}: {exc}")

        status_code = int(response.status_code)
        retryable = status_code in RETRYABLE_STATUS_CODES or 500 <= status_code <= 599
        if retryable and attempt < attempts:
            sleep(_retry_delay(response, attempt))
            continue
        if status_code != 200:
            return HttpResult(
                False, status_code, attempt, error=f"HTTP {status_code}")
        try:
            return HttpResult(True, status_code, attempt, data=decode(response))
        except (TypeError, ValueError) as exc:
            return HttpResult(
                False, status_code, attempt,
                error=f"invalid response body: {type(exc).__name__}: {exc}",
            )

    raise AssertionError("HTTP retry loop exited unexpectedly")


def get_json_result(url: str, *, params: dict | None = None,
                    headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
                    attempts: int = DEFAULT_ATTEMPTS,
                    sleep: Callable[[float], None] = time.sleep) -> HttpResult:
    request_headers = {"Accept": "application/json", **(headers or {})}
    return _get_result(
        url, params=params, headers=request_headers, timeout=timeout,
        attempts=attempts, decode=lambda response: response.json(), sleep=sleep,
    )


def get_text_result(url: str, *, params: dict | None = None,
                    headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
                    attempts: int = DEFAULT_ATTEMPTS,
                    sleep: Callable[[float], None] = time.sleep) -> HttpResult:
    return _get_result(
        url, params=params, headers=headers, timeout=timeout,
        attempts=attempts, decode=lambda response: response.text, sleep=sleep,
    )


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT) -> Optional[Any]:
    result = get_json_result(url, params=params, headers=headers, timeout=timeout)
    return result.data if result.ok else None


def get_text(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    result = get_text_result(url, params=params, headers=headers, timeout=timeout)
    return result.data if result.ok else None
