"""Tests for the semantic JD->resume coverage report (`analyze.coverage`)."""
import json
import os
import tempfile

from jobscope.analyze import coverage
from jobscope.core.config import load_config
from jobscope.core.model import Job, Resume
from jobscope.core.store import Store


JD = """About the role. Join our security team.

Responsibilities:
- Build detection pipelines in Python and deploy them on AWS
- Lead incident response and threat hunting across the fleet
- Collaborate with engineering teams to improve security posture

Requirements:
- 5+ years of experience in application security
- Strong proficiency with Kubernetes and Terraform
- Experience with Rust and formal verification methods

Benefits:
- Competitive salary and generous equity
- Unlimited paid time off and wellness stipend
"""


def _resume(**over) -> Resume:
    base = dict(
        full_name="Jane Doe", email="jane@example.com", phone="+1 555 0100",
        location="Remote", summary="Security engineer.",
        skills=["python", "aws", "kubernetes", "incident response", "threat hunting"],
        titles=["Security Engineer"], seniority="senior", years_experience=8, raw_text="")
    base.update(over)
    return Resume(**base)


def _job(desc: str = JD) -> Job:
    return Job(source="indeed", title="Senior Security Engineer", company="Acme",
               url="https://x/1", description=desc).ensure_id()


def _by(results, needle):
    return next(r for r in results if needle.lower() in r["text"].lower())


def test_extract_requirements_and_skips_benefits():
    reqs = coverage.extract_requirements(_job())
    texts = [r["text"] for r in reqs]
    assert any("detection pipelines" in t for t in texts)
    assert any(r["kind"] == "qualification" for r in reqs)   # "5+ years..."
    assert any(r["kind"] == "responsibility" for r in reqs)  # "Build ..."
    assert not any("salary" in t.lower() or "paid time off" in t.lower() for t in texts)


def test_filters_perks_keeps_skill_bullets_and_unescapes():
    jd = r"""Responsibilities:
- Build secure services in Python on AWS

Requirements:
- Experience with Azure, AWS, GCP
- 8\+ years of security experience

Perks & Culture:
- Global Award-Winning Culture
- Flexible Work Environment
- Rapid Growth Opportunities
- Company Sponsored Two-Way Transportation
- Exponential Career Growth

How to apply:
- Upload your resume to apply now
"""
    texts = [r["text"] for r in coverage.extract_requirements(_job(jd))]
    for perk in ("Culture", "Work Environment", "Growth Opportunities",
                 "Transportation", "Career Growth"):
        assert not any(perk in t for t in texts), f"perk leaked: {perk}"
    assert not any("upload" in t.lower() for t in texts)     # form-noise dropped
    assert any("Azure, AWS, GCP" in t for t in texts)        # lexicon-protected, kept
    assert any(t.startswith("8+ years") for t in texts)      # Markdown escape undone


def test_deterministic_assess_covered_partial_missing():
    reqs = coverage.extract_requirements(_job())
    res = coverage._assess_deterministic(_resume(), reqs)
    assert _by(res, "Build detection pipelines")["status"] == "covered"
    assert _by(res, "Kubernetes and Terraform")["status"] == "covered"  # kubernetes matches
    assert _by(res, "Rust and formal verification")["status"] == "missing"
    statuses = {r["status"] for r in res}
    assert {"covered", "missing"} <= statuses


def test_coverage_report_deterministic_offline(monkeypatch):
    from jobscope.core import ai
    monkeypatch.setattr(ai, "available", lambda cfg: False)
    rep = coverage.coverage_report({}, None, _resume(), _job())
    assert rep["mode"] == "deterministic"
    assert rep["total"] == rep["covered"] + rep["partial"] + rep["missing"]
    assert 0 <= rep["coverage_pct"] <= 100
    assert rep["suggestions"]  # missing/partial items produce tips


def test_ai_path_overrides_then_falls_back(monkeypatch):
    from jobscope.core import ai
    resume, job = _resume(), _job()
    n = len(coverage.extract_requirements(job))
    monkeypatch.setattr(ai, "available", lambda cfg: True)
    arr = [{"i": i, "status": "covered", "evidence": "resume", "suggestion": ""}
           for i in range(n)]
    monkeypatch.setattr(ai, "chat", lambda *a, **k: "```json\n" + json.dumps(arr) + "\n```")
    rep = coverage.coverage_report({}, None, resume, job)
    assert rep["mode"] == "ai" and rep["covered"] == n and rep["coverage_pct"] == 100.0

    monkeypatch.setattr(ai, "chat", lambda *a, **k: "sorry, no json here")
    rep2 = coverage.coverage_report({}, None, resume, job)
    assert rep2["mode"] == "deterministic"


def test_ai_incomplete_response_falls_back(monkeypatch):
    from jobscope.core import ai
    resume, job = _resume(), _job()
    monkeypatch.setattr(ai, "available", lambda cfg: True)
    # only one verdict for many requirements -> incomplete -> deterministic wins
    monkeypatch.setattr(ai, "chat",
                        lambda *a, **k: '[{"i":0,"status":"covered","evidence":"x"}]')
    rep = coverage.coverage_report({}, None, resume, job)
    assert rep["mode"] == "deterministic"


def test_parse_verdicts_handles_fences_and_garbage():
    txt = 'noise ```json\n[{"i":0,"status":"covered","evidence":"aws"}]\n``` tail'
    out = coverage._parse_verdicts(txt)
    assert out[0]["status"] == "covered"
    assert coverage._parse_verdicts("garbage") == {}
    assert coverage._parse_verdicts(None) == {}


def test_render_marks_and_no_requirements():
    rep = coverage.coverage_report({}, None, _resume(), _job())
    text = coverage.render_report(rep)
    assert "coverage report:" in text
    assert any(m in text for m in ("[+]", "[~]", "[-]"))

    empty = coverage.coverage_report({}, None, _resume(), _job("Too short."))
    assert empty["total"] == 0
    assert "no discrete requirements" in coverage.render_report(empty)


def test_run_offline_end_to_end(monkeypatch):
    from jobscope.core import ai
    monkeypatch.setattr(ai, "available", lambda cfg: False)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "c.db")
        store = Store(cfg["output"]["db_path"])
        assert coverage.run(cfg, store, "does-not-exist") == 1  # no job
        job = _job()
        store.upsert_job(job)
        assert coverage.run(cfg, store, job.id) == 1            # no resume yet
        store.save_resume(_resume())
        assert coverage.run(cfg, store, job.id) == 0
        store.close()
