"""Tests for the resume ATS parse check (`analyze.atscheck`). Deterministic, offline."""
import os
import tempfile

from jobscope.analyze import atscheck
from jobscope.apply import tailor
from jobscope.core.config import load_config
from jobscope.core.model import Job, Resume
from jobscope.core.store import Store


CLEAN_TEXT = """# Jane Doe
jane@example.com
+1 555 0100
Bengaluru, India

## Summary
Security engineer.

## Skills
python, aws, kubernetes, iam, threat modeling, terraform

## Experience
### Security Engineer - Acme (2018 - Present)
- Built detections and shipped secure code review.
"""


def _resume(**over) -> Resume:
    base = dict(
        full_name="Jane Doe",
        email="jane@example.com",
        phone="+1 555 0100",
        location="Bengaluru, India",
        skills=["python", "aws", "kubernetes", "iam", "threat modeling", "terraform"],
        titles=["Security Engineer"],
        seniority="senior",
        years_experience=8,
        raw_text=CLEAN_TEXT,
        source_path="/x/resume.md",
    )
    base.update(over)
    return Resume(**base)


def _job() -> Job:
    return Job(source="indeed", title="Senior Security Engineer", company="Acme",
               url="https://x/1",
               description="We want python, aws, kubernetes, iam, terraform and sast."
               ).ensure_id()


def test_clean_resume_scores_high_no_warnings():
    rep = atscheck.ats_report(_resume())
    assert rep["score"] == 100
    assert rep["warnings"] == []
    assert rep["name"] == "Jane Doe"
    assert "python" in rep["skills"]


def test_missing_contact_and_skills_are_errors():
    rep = atscheck.ats_report(_resume(email="", phone="", skills=[], raw_text="Jane Doe\nsome prose"))
    codes = {w["code"]: w["level"] for w in rep["warnings"]}
    assert codes.get("no_email") == "error"
    assert codes.get("no_skills") == "error"
    assert codes.get("no_phone") == "warn"
    assert rep["score"] < 60  # multiple errors tank the score


def test_few_skills_and_no_skills_section():
    rep = atscheck.ats_report(_resume(skills=["python", "aws"], raw_text="Jane Doe\npython and aws work"))
    codes = {w["code"] for w in rep["warnings"]}
    assert "few_skills" in codes
    assert "no_skills_section" in codes  # skills present but no heading in the text


def test_tables_and_glyphs_flagged():
    text = CLEAN_TEXT + "\n| Skill | Level |\n| python | expert |\n| aws | expert |\n\ufb01nance"
    rep = atscheck.ats_report(_resume(raw_text=text))
    codes = {w["code"] for w in rep["warnings"]}
    assert "tables" in codes
    assert "risky_glyphs" in codes  # the fi-ligature (U+FB01)


def test_multi_column_layout_flagged():
    rows = "\n".join(f"Security Engineer        202{i} - 202{i+1}" for i in range(7))
    rep = atscheck.ats_report(_resume(raw_text="# Jane Doe\n" + rows))
    assert any(w["code"] == "multi_column" for w in rep["warnings"])


def test_replacement_char_is_error():
    rep = atscheck.ats_report(_resume(raw_text=CLEAN_TEXT + "\nbroken \ufffd text"))
    codes = {w["code"]: w["level"] for w in rep["warnings"]}
    assert codes.get("replacement_chars") == "error"


def test_image_pdf_flagged():
    rep = atscheck.ats_report(_resume(source_path="/x/scan.pdf", raw_text="Jane Doe"))
    assert any(w["code"] == "image_pdf" and w["level"] == "error" for w in rep["warnings"])


def test_coverage_matches_tailor_and_renders():
    resume, job = _resume(), _job()
    cov = atscheck.coverage(resume, job)
    assert cov == tailor.analyze(resume, job)
    assert 0 <= cov["coverage"] <= 100
    text = atscheck.render_report(atscheck.ats_report(resume), job=job, cov=cov)
    assert "JD keyword coverage" in text
    assert "matched" in text and "missing" in text


def test_render_clean_says_no_issues():
    text = atscheck.render_report(atscheck.ats_report(_resume()))
    assert "no formatting issues detected" in text
    assert "ATS-friendliness: 100/100" in text


def test_run_offline_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "a.db")
        store = Store(cfg["output"]["db_path"])
        assert atscheck.run(cfg, store) == 1  # no resume imported yet

        store.save_resume(_resume())
        assert atscheck.run(cfg, store) == 0

        job = _job()
        store.upsert_job(job)
        assert atscheck.run(cfg, store, job_id=job.id) == 0
        assert atscheck.run(cfg, store, job_id="does-not-exist") == 1
        store.close()
