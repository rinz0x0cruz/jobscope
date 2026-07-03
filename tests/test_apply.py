import os
import tempfile

from jobscope.apply import apply
from jobscope.core.config import load_config
from jobscope.core.model import Job, Resume
from jobscope.core.store import Store


def _seed(store):
    store.save_resume(Resume(
        full_name="Jane Doe", email="jane@example.com", phone="+1 555 0100",
        location="Remote", skills=["python", "aws", "iam"], titles=["Security Engineer"],
        seniority="senior", years_experience=8,
        links={"linkedin": "https://linkedin.com/in/jane"},
        raw_text="# Jane Doe\n\n## Skills\npython, aws\n"))
    job = Job(source="indeed", title="Security Engineer", company="Acme",
              url="https://boards.greenhouse.io/acme/jobs/123",
              description="python aws iam terraform").ensure_id()
    store.upsert_job(job)
    return job


def test_prep_builds_package_offline(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
        cfg["apply"]["package_dir"] = os.path.join(tmp, "apps")
        cfg["email"]["enabled"] = False

        store = Store(cfg["output"]["db_path"])
        job = _seed(store)

        assert apply.prep(cfg, store, job.id) == 0
        app = {a["job_id"]: a for a in store.applications()}[job.id]
        assert app["status"] == "prepared"
        pkg = app["package_dir"]
        for f in ("tailored_resume.md", "cover_letter.md", "filled-answers.md",
                  "application.md", "analysis.md"):
            assert os.path.exists(os.path.join(pkg, f)), f
        answers = open(os.path.join(pkg, "filled-answers.md"), encoding="utf-8").read()
        assert "jane@example.com" in answers
        idx = open(os.path.join(pkg, "application.md"), encoding="utf-8").read()
        assert "greenhouse.io" in idx
        store.close()


def test_public_ats_detection():
    assert apply._is_public_ats("https://boards.greenhouse.io/acme/jobs/1")
    assert apply._is_public_ats("https://jobs.lever.co/acme/xyz")
    assert not apply._is_public_ats("https://www.linkedin.com/jobs/view/123")


def test_profile_fields_mapping():
    r = Resume(full_name="Jane Doe", email="j@x.com", phone="555",
               links={"linkedin": "L"})
    fm = apply._profile_fields(r)
    assert fm["first name"] == "Jane" and fm["last name"] == "Doe"
    assert fm["email"] == "j@x.com" and fm["linkedin"] == "L"
