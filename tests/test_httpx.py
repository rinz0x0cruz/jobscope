from unittest.mock import Mock

import requests

from jobscope.core import httpx


def _response(status: int, *, data=None, text: str = "", headers=None):
    response = Mock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = data
    response.text = text
    return response


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