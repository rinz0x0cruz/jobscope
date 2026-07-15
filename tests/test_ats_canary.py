from jobscope.core.httpx import HttpResult
from jobscope.core import httpx
from jobscope.ingest import ats_canary
from jobscope.ingest.ats import BoardFetchResult, BoardStatus


def _http(data=None, *, ok=True, status=200, error=""):
    return HttpResult(
        ok=ok, status_code=status, attempts=1, data=data, error=error,
    )


def test_canary_treats_valid_empty_board_as_healthy(monkeypatch):
    responses = {
        "greenhouse": _http({"jobs": []}),
        "lever": _http([{
            "text": "Security Engineer", "categories": {"location": "Remote"},
            "hostedUrl": "https://example.test/job", "createdAt": 0,
        }]),
    }
    monkeypatch.setattr(
        httpx, "get_json_result",
        lambda url, **_kwargs: responses["lever" if "lever.co" in url else "greenhouse"],
    )
    lines = []

    summary = ats_canary.check_boards(
        [("Empty Co", ("greenhouse", "empty")), ("Live Co", ("lever", "live"))],
        emit=lines.append,
    )

    assert summary.checked == 2 and summary.healthy == 2
    assert summary.unhealthy == 0 and summary.jobs == 1
    assert summary.statuses == {"empty": 1, "ok": 1}
    assert any("Empty Co" in line and "healthy" in line for line in lines)


def test_canary_reports_partial_and_failed_boards(monkeypatch):
    def fetch(company, provider, slug):
        if company == "Partial Co":
            return BoardFetchResult(
                company, provider, slug, BoardStatus.PARTIAL,
                detail="1 malformed posting(s)", attempts=1, status_code=200,
            )
        return BoardFetchResult(
            company, provider, slug, BoardStatus.ERROR,
            detail="HTTP 503 after 3 attempts", attempts=3, status_code=503,
        )

    monkeypatch.setattr(ats_canary, "fetch_company_result", fetch)

    summary = ats_canary.check_boards([
        ("Partial Co", ("ashby", "partial")),
        ("Failed Co", ("greenhouse", "failed")),
    ], emit=lambda _line: None)

    assert summary.healthy == 0 and summary.unhealthy == 2
    assert summary.statuses == {"error": 1, "partial": 1}


def test_canary_main_exit_status(monkeypatch):
    unhealthy = ats_canary.CanarySummary(1, 0, 1, 0, {"error": 1})
    monkeypatch.setattr(ats_canary, "check_boards", lambda **_kwargs: unhealthy)

    assert ats_canary.main([]) == 1
    assert ats_canary.main(["--allow-unhealthy"]) == 0