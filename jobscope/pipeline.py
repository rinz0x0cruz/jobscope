"""One-shot pipeline: scan -> match -> enrich -> prep top picks -> digest.

This is the "just works" entry point that chains the individual commands and, if
email is enabled, sends a single digest instead of one message per job.
"""
from __future__ import annotations

from . import apply, email, enrich, match, scrape


def run(cfg: dict, store, do_prep: bool = True) -> int:
    print("== scan ==")
    scrape.run(cfg, store)
    print("\n== match ==")
    match.run(cfg, store)
    print("\n== enrich ==")
    enrich.run(cfg, store)

    prepared = []
    if do_prep:
        top_n = cfg["apply"].get("auto_prep_top", 3)
        picks = [j for j in store.jobs(order_by_score=True) if j.tier in ("Strong", "Good")][:top_n]
        if picks:
            print(f"\n== prep top {len(picks)} ==")
            for j in picks:
                apply.prep(cfg, store, j.id, notify=False)
                prepared.append(j)

    _digest(cfg, store, prepared)
    print("\n  pipeline complete. Review: python -m jobscope dashboard --open")
    return 0


def _digest(cfg: dict, store, prepared: list) -> None:
    ranked = store.jobs(order_by_score=True)
    strong = [j for j in ranked if j.tier == "Strong"]
    good = [j for j in ranked if j.tier == "Good"]
    lines = [
        "jobscope run summary",
        f"  ranked: {len(ranked)} jobs  |  Strong {len(strong)}, Good {len(good)}",
        f"  prepared packages: {len(prepared)}",
        "",
        "Top picks:",
    ]
    for j in (prepared or (strong + good)[:5]):
        lines.append(f"  [{j.score}] {j.title} @ {j.company} -> {j.url}")
    text = "\n".join(lines)
    print("\n" + text)
    if cfg.get("email", {}).get("enabled"):
        email.send(cfg, f"[jobscope] {len(prepared)} prepared, {len(strong)} strong matches", text)
