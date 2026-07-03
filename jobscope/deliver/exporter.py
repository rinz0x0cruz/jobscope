"""Export ranked jobs to JSON or CSV."""
from __future__ import annotations

import csv
import json
from typing import Optional


def run(store, fmt: str = "json", out: Optional[str] = None) -> int:
    jobs = store.jobs(order_by_score=True)
    out = out or f"data/export.{fmt}"
    if fmt == "json":
        with open(out, "w", encoding="utf-8") as fh:
            json.dump([j.to_dict() for j in jobs], fh, indent=2)
    else:
        cols = ["score", "tier", "title", "company", "location", "salary_min",
                "salary_max", "currency", "url", "date_posted", "rationale"]
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for j in jobs:
                d = j.to_dict()
                w.writerow([d.get(c, "") for c in cols])
    print(f"  exported {len(jobs)} jobs -> {out}")
    return 0
