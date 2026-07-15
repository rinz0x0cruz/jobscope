"""Probe every curated public ATS board and report mapping health."""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .ats import BoardFetchResult, BoardStatus, COMPANY_BOARDS, fetch_company_result

HEALTHY_STATUSES = frozenset({BoardStatus.OK, BoardStatus.EMPTY})


@dataclass(frozen=True, slots=True)
class CanarySummary:
    checked: int
    healthy: int
    unhealthy: int
    jobs: int
    statuses: dict[str, int]


def check_boards(
    entries: Iterable[tuple[str, tuple[str, str]]] | None = None,
    *,
    emit: Callable[[str], None] = print,
    workers: int = 6,
) -> CanarySummary:
    boards = sorted(entries if entries is not None else COMPANY_BOARDS.items())
    counts: Counter[str] = Counter()
    total_jobs = 0
    unhealthy = 0

    def probe(entry: tuple[str, tuple[str, str]]) -> BoardFetchResult:
        company, (provider, slug) = entry
        try:
            return fetch_company_result(company, provider, slug)
        except Exception as exc:  # noqa: BLE001 - canary must identify the failed mapping
            return BoardFetchResult(
                company, provider, slug, BoardStatus.ERROR,
                detail=f"unexpected probe failure: {exc}",
            )

    if boards:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(boards)))) as executor:
            results = list(executor.map(probe, boards))
    else:
        results = []

    for (company, (provider, slug)), result in zip(boards, results):
        counts[result.status.value] += 1
        total_jobs += len(result.jobs)
        healthy = result.status in HEALTHY_STATUSES
        if not healthy:
            unhealthy += 1
        label = "healthy" if healthy else "unhealthy"
        detail = f" - {result.detail}" if result.detail else ""
        emit(
            f"[{label}] {company}: {provider}/{slug} "
            f"{result.status.value}, {len(result.jobs)} job(s), "
            f"{result.attempts} attempt(s){detail}"
        )

    summary = CanarySummary(
        checked=len(boards),
        healthy=len(boards) - unhealthy,
        unhealthy=unhealthy,
        jobs=total_jobs,
        statuses=dict(sorted(counts.items())),
    )
    emit(
        f"ATS canary: {summary.healthy}/{summary.checked} healthy, "
        f"{summary.unhealthy} unhealthy, {summary.jobs} job(s) observed"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unhealthy",
        action="store_true",
        help="report unhealthy mappings without returning a failing exit status",
    )
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    summary = check_boards(workers=args.workers)
    return 0 if args.allow_unhealthy or summary.unhealthy == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())