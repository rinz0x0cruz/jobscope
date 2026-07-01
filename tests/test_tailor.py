import os
import tempfile

from jobscope import tailor
from jobscope.config import load_config
from jobscope.model import Job, Resume
from jobscope.store import Store


def _resume():
    return Resume(
        full_name="Jane Doe",
        email="jane@example.com",
        location="Remote",
        summary="Security engineer.",
        skills=["python", "aws", "kubernetes", "iam", "threat modeling"],
        titles=["Security Engineer"],
        seniority="senior",
        years_experience=8,
        raw_text="# Jane Doe\n\n## Summary\nSecurity engineer.\n\n## Skills\npython, aws\n",
    )


def _job():
    return Job(source="indeed", title="Senior Security Engineer", company="Acme",
               url="https://x/1",
               description="We want python, aws, kubernetes, iam, terraform and sast experience."
               ).ensure_id()


def test_analyze_matches_and_gaps():
    a = tailor.analyze(_resume(), _job())
    assert "python" in [m.lower() for m in a["matched"]]
    assert "terraform" in a["missing"] or "sast" in a["missing"]
    assert 0 <= a["coverage"] <= 100


def test_run_produces_package_offline(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)  # force deterministic path
    with tempfile.TemporaryDirectory() as tmp:
        cfg = load_config(None)
        cfg["output"]["db_path"] = os.path.join(tmp, "t.db")
        cfg["apply"]["package_dir"] = os.path.join(tmp, "apps")

        store = Store(cfg["output"]["db_path"])
        store.save_resume(_resume())
        job = _job()
        store.upsert_job(job)

        rc = tailor.run(cfg, store, job.id)
        assert rc == 0

        apps = store.applications()
        assert apps and apps[0]["status"] == "prepared"
        pkg = apps[0]["package_dir"]
        assert os.path.exists(os.path.join(pkg, "tailored_resume.md"))
        assert os.path.exists(os.path.join(pkg, "cover_letter.md"))
        assert os.path.exists(os.path.join(pkg, "analysis.md"))

        resume_md = open(os.path.join(pkg, "tailored_resume.md"), encoding="utf-8").read()
        assert "Priority Skills for Acme" in resume_md
        assert "Jane Doe" in resume_md
        store.close()
