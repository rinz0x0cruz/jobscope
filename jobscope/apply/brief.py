"""`jobscope brief <job_id>` -- print the blunt company brief for a job.

Uses the stored brief if enrichment already produced one; otherwise builds it on
demand from whatever enrichment exists (plus job-level red flags).
"""
from __future__ import annotations

from jobscope import enrich as enrichment
from jobscope.enrich import brief as _brief


def run(cfg: dict, store, job_id: str) -> int:
    job = store.get_job(job_id)
    if job is None:
        print(f"  job not found: {job_id}")
        return 1
    enr = enrichment.for_job(store, job)
    data = (enr or {}).get("brief")
    if not data:
        data = _brief.build(cfg, store, job.company, job, enr or {})
        store.save_job_analysis(
            job.id, resume_base=job.resume_base or "",
            version=enrichment.ANALYSIS_VERSION, brief=data,
        )

    print(f"  Company brief -- {job.company} ({job.title})")
    print(f"  {'[AI]' if data.get('ai') else '[facts]'}\n")
    print(data.get("text", "(no data)"))
    return 0
