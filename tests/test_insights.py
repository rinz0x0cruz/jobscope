"""Tests for skill-gap insights and the blunt company brief."""
import os
import tempfile

from jobscope import insights
from jobscope.config import load_config
from jobscope.enrich import brief
from jobscope.model import Job, Resume
from jobscope.store import Store


def _store(tmp):
    return Store(os.path.join(tmp, "i.db"))


def test_skill_gap_finds_missing_skills():
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.save_resume(Resume(skills=["python", "aws"], seniority="mid"))
        j1 = Job(title="Sec Eng", company="A", url="1", tier="Good",
                 description="need python, kubernetes, splunk, siem").ensure_id()
        j2 = Job(title="Sec Eng", company="B", url="2", tier="Strong",
                 description="need python, kubernetes, terraform").ensure_id()
        for j in (j1, j2):
            store.upsert_job(j)
            store.update_score(j.id, 70, j.tier, "x")
        considered, gaps = insights.skill_gap(store, top=10)
        assert considered == 2
        skills = {g[0] for g in gaps}
        assert "kubernetes" in skills          # appears in both -> top gap
        assert "python" not in skills          # already on resume
        top = gaps[0]
        assert top[0] == "kubernetes" and top[1] == 2
        store.close()


def test_skill_gap_ignores_skip_tier():
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        store.save_resume(Resume(skills=["python"]))
        j = Job(title="x", company="A", url="1", tier="Skip",
                description="kubernetes terraform").ensure_id()
        store.upsert_job(j)
        store.update_score(j.id, 10, "Skip", "x")
        considered, gaps = insights.skill_gap(store)
        assert considered == 0 and gaps == []
        store.close()


def _cfg():
    return load_config(None)


def test_brief_is_risk_forward_and_deterministic(monkeypatch):
    monkeypatch.delenv("JOBSCOPE_AI_API_KEY", raising=False)  # force deterministic
    job = Job(title="Cyber Security Engineer", company="Acme",
              description="python aws. Active security clearance required. US citizens only.")
    enr = {
        "stock": {"public": False},
        "reddit": {"count": 5, "sentiment": "negative"},
        "news": [{"title": "Acme announces layoffs across divisions", "link": "x"}],
    }
    data = brief.build(_cfg(), None, "Acme", job, enr)
    assert data["ai"] is False
    text = data["text"]
    assert "Risks" in text
    # concrete risks surfaced, not glossed over
    assert any("clearance" in r.lower() for r in data["risks"])
    assert any("private" in r.lower() or "pre-ipo" in r.lower() for r in data["facts"])
    assert any("layoff" in r.lower() for r in data["risks"])
    assert any("negative" in r.lower() for r in data["risks"])


def test_brief_flags_missing_salary():
    job = Job(title="Engineer", company="B", description="build things")
    data = brief.build(_cfg(), None, "B", job, {})
    assert any("no salary" in r.lower() for r in data["risks"])
