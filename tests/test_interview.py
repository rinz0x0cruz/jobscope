"""Tests for the interview-prep hub (`apply.interview`). Deterministic, offline."""
import os
import tempfile

from jobscope.apply import interview
from jobscope.core.config import load_config
from jobscope.core.model import Contact, Job, Resume
from jobscope.core.store import Store


JD = """Responsibilities:
- Build detection pipelines in Python and deploy on AWS
- Lead incident response and threat hunting across the fleet
- Design secure cloud architecture on Azure

Requirements:
- 5+ years of security experience
- Experience with Kubernetes and Terraform
"""


def _resume():
    return Resume(
        full_name="Jane Doe", email="jane@example.com",
        skills=["python", "aws", "azure", "kubernetes", "incident response", "threat hunting"],
        titles=["Security Engineer"], seniority="senior", years_experience=8,
        summary="Security engineer.", raw_text="")


def _job():
    return Job(source="indeed", title="Senior Security Engineer", company="Acme",
               url="https://x/1", description=JD, score=82.0, tier="Strong").ensure_id()


def _store(tmp):
    cfg = load_config(None)
    cfg["output"]["db_path"] = os.path.join(tmp, "i.db")
    return cfg, Store(cfg["output"]["db_path"])


def test_prep_sheet_assembles_fit_topics_star():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        job = _job()
        store.upsert_job(job)
        s = interview.prep_sheet(cfg, store, job, _resume())
        assert s["tier"] == "Strong" and s["score"] == 82.0
        assert "python" in [x.lower() for x in s["strengths"]]
        assert any("detection pipelines" in t for t in s["topics"])
        assert s["star"] and 0 <= s["coverage"] <= 100
        store.close()


def test_render_sheet_sections_and_hints():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        job = _job()
        store.upsert_job(job)
        text = interview.render_sheet(job, interview.prep_sheet(cfg, store, job, _resume()))
        assert "Interview prep" in text
        assert "lead with your strengths" in text
        assert "STAR stories" in text
        assert "referral path" in text
        assert "your notes:" in text            # none yet -> hint
        store.close()


def test_note_appends_and_persists():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        job = _job()
        store.upsert_job(job)
        store.save_resume(_resume())
        assert interview.run(cfg, store, job.id, note="recruiter: Sam; salary TBD") == 0
        assert "recruiter: Sam" in store.get_application(job.id)["notes"]
        interview.run(cfg, store, job.id, note="phone screen Tuesday")
        notes = store.get_application(job.id)["notes"]
        assert "recruiter: Sam" in notes and "phone screen Tuesday" in notes  # both retained
        store.close()


def test_note_saved_without_resume():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        job = _job()
        store.upsert_job(job)                    # no resume imported
        assert interview.run(cfg, store, job.id, note="hi") == 0
        assert "hi" in store.get_application(job.id)["notes"]
        store.close()


def test_run_bad_job_and_missing_resume():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        assert interview.run(cfg, store, "nope") == 1     # bad job id
        job = _job()
        store.upsert_job(job)
        assert interview.run(cfg, store, job.id) == 1     # no resume, no note
        store.close()


def test_brief_and_referrals_surface_when_present():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, store = _store(tmp)
        job = _job()
        store.upsert_job(job)
        store.save_contacts([Contact(id="c1", company="Acme", name="Dev", source="github",
                                     profile_url="https://github.com/dev", outreach="Hi Dev")])
        store.save_enrichment("Acme", brief={"text": "Acme is pre-IPO. Risks: comp opaque.",
                                              "ai": False})
        text = interview.render_sheet(job, interview.prep_sheet(cfg, store, job, _resume()))
        assert "company brief:" in text and "pre-IPO" in text
        assert "1 profile(s)" in text
        store.close()
