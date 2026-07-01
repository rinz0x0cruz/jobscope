"""`jobscope brief <job_id>` -- print the blunt company brief for a job.

Uses the stored brief if enrichment already produced one; otherwise builds it on
demand from whatever enrichment exists (plus job-level red flags).
"""
from __future__ import annotations

from .enrich import brief as _brief


def run(cfg: dict, store, job_id: str) -> int:
    job = store.get_job(job_id)
    if job is None:
        print(f"  job not found: {job_id}")
        return 1
    enr = store.get_enrichment(job.company) if job.company else {}
    data = (enr or {}).get("brief")
    if not data:
        data = _brief.build(cfg, store, job.company, job, enr or {})
        if job.company:
            store.save_enrichment(job.company, brief=data)

    print(f"  Company brief -- {job.company} ({job.title})")
    print(f"  {'[AI]' if data.get('ai') else '[facts]'}\n")
    print(data.get("text", "(no data)"))
    return 0
