"""Integration: the AI/quorum seniority tie-breaker demotes ambiguous leakers, and
is a strict no-op when AI is off."""
import os

from jobscope.core import ai
from jobscope.analyze import match
from jobscope.core.config import load_config
from jobscope.core.model import Job
from jobscope.analyze.resume import parse_resume
from jobscope.core.store import Store

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "resume.md")


def _cfg(db):
    cfg = load_config(None)
    cfg["output"]["db_path"] = db
    cfg["filters"]["max_years_experience"] = 3
    cfg["match"]["ai_seniority_tiebreak"] = True
    cfg["ai"]["enabled"] = True
    return cfg


def _ambiguous_job(url):
    # plain title, no level word, no stated years -> deterministically "ambiguous"
    return Job(source="indeed", title="Security Engineer", company="Acme", url=url,
               is_remote=True, salary_min=150000, salary_max=200000,
               description="python aws kubernetes iam threat modeling terraform; "
                           "build and operate the security paved road " * 4).ensure_id()


def test_tiebreak_demotes_ambiguous_senior(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    store = Store(db)
    store.save_resume(parse_resume(FIX))
    job = _ambiguous_job("a1")
    store.upsert_job(job)

    monkeypatch.setattr(ai, "available", lambda cfg: True)
    monkeypatch.setattr(ai, "chat", lambda *a, **k: '{"level": "senior", "required_years": 6}')

    match.run(_cfg(db), store)

    j = store.get_job(job.id)
    assert j.ai_seniority == "senior"
    assert j.ai_required_years == 6.0
    assert j.tier == "Skip"                     # 6y > cap 3 -> filtered
    assert "AI:senior" in (j.rationale or "")


def test_tiebreak_noop_when_ai_off(monkeypatch, tmp_path):
    db = str(tmp_path / "t2.db")
    store = Store(db)
    store.save_resume(parse_resume(FIX))
    job = _ambiguous_job("b1")
    store.upsert_job(job)

    monkeypatch.setattr(ai, "available", lambda cfg: False)
    called = []
    monkeypatch.setattr(ai, "chat", lambda *a, **k: called.append(1) or None)

    match.run(_cfg(db), store)

    j = store.get_job(job.id)
    assert not called                           # classifier never consulted
    assert (j.ai_seniority or "") == ""
    assert j.tier != "Skip"                     # stays a real match
