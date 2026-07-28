"""Scan user-selected companies through reviewed public ATS adapters."""
from __future__ import annotations


def run(cfg: dict, store, *, mode: str = "all") -> int:
    if mode not in {"all", "monitored"}:
        raise ValueError(f"invalid scan mode: {mode}")

    from . import monitor

    summary = monitor.scan_active_monitors(cfg, store)
    print(
        "  monitored portals: "
        f"{summary['successful']}/{summary['companies']} healthy, "
        f"{summary['matched']} matched ({summary['new']} new)"
    )
    return 0