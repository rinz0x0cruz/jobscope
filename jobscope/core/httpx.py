"""HTTP helpers with bounded retries and best-effort compatibility wrappers.

Every enricher is best-effort: network failures return None/empty rather than
raising, so one dead source never breaks a run. Callers that need source-health
detail can use the ``*_result`` variants.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 jobscope/0.1"
)
DEFAULT_TIMEOUT = 12
DEFAULT_ATTEMPTS = 3
MAX_RETRY_DELAY = 5.0
RETRYABLE_STATUS_CODES = frozenset({408, 429})
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 5


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


def _is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    return bool(
        address.is_global
        and not address.is_link_local
        and not address.is_loopback
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _public_destinations(url: str) -> tuple[Any, int, tuple[str, ...]]:
    try:
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("invalid outbound URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("outbound URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("outbound URL credentials are not allowed")

    hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("outbound URL must use a public host")
    try:
        addresses = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        try:
            addresses = list({
                info[4][0]
                for info in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            })
        except OSError as exc:
            raise ValueError("outbound URL host could not be resolved") from exc
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ValueError("outbound URL resolved to a non-public address")
    ordered = tuple(sorted(set(addresses), key=lambda value: (
        ipaddress.ip_address(value.split("%", 1)[0]).version,
        int(ipaddress.ip_address(value.split("%", 1)[0])),
    )))
    return parsed, port, ordered


def _validate_public_url(url: str) -> None:
    _public_destinations(url)


def _request_pinned(url: str, address: str, *, params: dict | None,
                    headers: dict[str, str], timeout: int):
    import certifi
    import requests
    import urllib3
    from requests.structures import CaseInsensitiveDict

    prepared = requests.Request("GET", url, params=params, headers=headers).prepare()
    parsed = urlparse(prepared.url)
    hostname = (parsed.hostname or "").encode("idna").decode("ascii")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    default_port = 443 if parsed.scheme == "https" else 80
    host_value = f"[{hostname}]" if ":" in hostname else hostname
    if port != default_port:
        host_value = f"{host_value}:{port}"
    request_headers = dict(prepared.headers)
    request_headers["Host"] = host_value
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    if parsed.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            address,
            port=port,
            timeout=timeout,
            retries=False,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            assert_hostname=hostname,
            server_hostname=hostname,
        )
    else:
        pool = urllib3.HTTPConnectionPool(
            address, port=port, timeout=timeout, retries=False,
        )
    try:
        raw = pool.urlopen(
            "GET", target, headers=request_headers, redirect=False,
            retries=False, preload_content=True, timeout=timeout,
        )
        response = requests.Response()
        response.status_code = int(raw.status)
        response.headers = CaseInsensitiveDict(raw.headers)
        response._content = bytes(raw.data)
        response.url = prepared.url
        response.request = prepared
        response.raw = raw
        response.encoding = requests.utils.get_encoding_from_headers(response.headers)
        return response
    except (urllib3.exceptions.HTTPError, OSError, ssl.SSLError) as exc:
        raise requests.ConnectionError(str(exc)) from exc
    finally:
        pool.close()


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT):
    import requests
    h = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    current = url
    current_params = params
    for _ in range(MAX_REDIRECTS + 1):
        _, _, addresses = _public_destinations(current)
        response = None
        last_error = None
        for address in addresses:
            try:
                response = _request_pinned(
                    current, address, params=current_params, headers=h, timeout=timeout,
                )
                break
            except requests.RequestException as exc:
                last_error = exc
        if response is None:
            raise last_error or requests.ConnectionError("no public destination available")
        location = response.headers.get("Location", "")
        if response.status_code not in REDIRECT_STATUS_CODES or not location:
            return response
        current = urljoin(str(response.url or current), location)
        current_params = None
        response.close()
    raise requests.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")


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
