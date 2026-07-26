from unittest.mock import Mock

import pytest
import requests

from jobscope.core import httpx


def _response(status: int, *, data=None, text: str = "", headers=None):
    response = Mock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = data
    response.text = text
    return response


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://localhost/admin",
    "http://127.0.0.1/admin",
    "http://10.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/admin",
    "https://user:password@example.com/",  # pragma: allowlist secret
    "http://jobscope.railway.internal/",
])
def test_public_url_validation_rejects_non_public_destinations(url):
    with pytest.raises(ValueError, match="outbound URL|non-public"):
        httpx._validate_public_url(url)


def test_public_url_validation_rejects_mixed_dns_answers(monkeypatch):
    monkeypatch.setattr(httpx.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (httpx.socket.AF_INET, httpx.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (httpx.socket.AF_INET, httpx.socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443)),
    ])

    with pytest.raises(ValueError, match="non-public"):
        httpx._validate_public_url("https://example.com/jobs")


def test_get_rejects_redirect_to_private_address(monkeypatch):
    redirected = _response(302, headers={"Location": "http://127.0.0.1/private"})
    redirected.url = "https://example.com/jobs"
    monkeypatch.setattr(httpx.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (httpx.socket.AF_INET, httpx.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ])
    request = Mock(return_value=redirected)
    monkeypatch.setattr(httpx, "_request_pinned", request)

    with pytest.raises(ValueError, match="non-public"):
        httpx.get("https://example.com/jobs")

    assert request.call_count == 1


def test_get_connects_to_the_vetted_ip_without_second_dns_lookup(monkeypatch):
    resolutions = {"count": 0}

    def resolve(*_args, **_kwargs):
        resolutions["count"] += 1
        address = "93.184.216.34" if resolutions["count"] == 1 else "127.0.0.1"
        return [(httpx.socket.AF_INET, httpx.socket.SOCK_STREAM, 6, "", (address, 443))]

    monkeypatch.setattr(httpx.socket, "getaddrinfo", resolve)
    response = _response(200, text="ok")
    response.url = "https://example.com/jobs"
    request = Mock(return_value=response)
    monkeypatch.setattr(httpx, "_request_pinned", request)

    result = httpx.get("https://example.com/jobs")

    assert result.status_code == 200
    assert resolutions["count"] == 1
    assert request.call_args.args[:2] == (
        "https://example.com/jobs", "93.184.216.34",
    )


def test_json_result_retries_transient_status(monkeypatch):
    responses = [
        _response(503, headers={"Retry-After": "2"}),
        _response(200, data={"jobs": []}),
    ]
    sleeps = []
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: responses.pop(0))

    result = httpx.get_json_result("https://example.test", sleep=sleeps.append)

    assert result.ok and result.data == {"jobs": []}
    assert result.status_code == 200 and result.attempts == 2
    assert sleeps == [2.0]


def test_json_result_retries_request_exception(monkeypatch):
    calls = {"count": 0}

    def request(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.Timeout("slow")
        return _response(200, data={"ok": True})

    sleeps = []
    monkeypatch.setattr(httpx, "get", request)

    result = httpx.get_json_result("https://example.test", sleep=sleeps.append)

    assert result.ok and result.attempts == 3
    assert sleeps == [0.5, 1.0]


def test_json_result_does_not_retry_permanent_or_invalid_response(monkeypatch):
    sleeps = []
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _response(404))
    missing = httpx.get_json_result("https://example.test", sleep=sleeps.append)
    assert not missing.ok and missing.error == "HTTP 404"
    assert missing.attempts == 1 and sleeps == []

    invalid_response = _response(200)
    invalid_response.json.side_effect = ValueError("bad json")
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: invalid_response)
    invalid = httpx.get_json_result("https://example.test", sleep=sleeps.append)
    assert not invalid.ok and invalid.error.startswith("invalid response body")
    assert invalid.attempts == 1 and sleeps == []


def test_retry_after_is_bounded(monkeypatch):
    responses = [
        _response(429, headers={"Retry-After": "3600"}),
        _response(200, text="ok"),
    ]
    sleeps = []
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: responses.pop(0))

    result = httpx.get_text_result("https://example.test", sleep=sleeps.append)

    assert result.ok and result.data == "ok"
    assert sleeps == [httpx.MAX_RETRY_DELAY]


def test_compatibility_helpers_return_none_on_failure(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _response(403))

    assert httpx.get_json("https://example.test") is None
    assert httpx.get_text("https://example.test") is None