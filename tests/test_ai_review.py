"""Tests for the optional (off-by-default) quorum judge second-opinion on matches."""
from jobscope.analyze.match import ai_review
from jobscope.core.config import load_config
from jobscope.core.model import Job, Resume

_TIERS = {"strong": 75, "good": 55, "stretch": 35}


def test_near_boundary():
    assert ai_review.near_boundary(73, _TIERS, 8)       # near the Strong cut (75)
    assert ai_review.near_boundary(57, _TIERS, 8)       # near the Good cut (55)
    assert not ai_review.near_boundary(90, _TIERS, 8)   # comfortably clear


def test_tier_of():
    assert ai_review._tier_of(80, _TIERS) == "Strong"
    assert ai_review._tier_of(60, _TIERS) == "Good"
    assert ai_review._tier_of(40, _TIERS) == "Stretch"
    assert ai_review._tier_of(10, _TIERS) == "Skip"


def test_review_job_none_when_ai_off():
    cfg = load_config(None)  # ai + quorum off by default -> ai.score returns None
    job = Job(source="x", title="Security Engineer", company="Acme")
    assert ai_review.review_job(cfg, None, job, Resume(), 73.0, "Good", _TIERS) is None


def test_review_job_flags_divergence(monkeypatch):
    from jobscope.core import ai
    monkeypatch.setattr(ai, "score",
                        lambda *a, **k: {"score": 95.0, "sub_scores": {}, "rationale": "r"})
    cfg = load_config(None)
    job = Job(source="x", title="Security Engineer", company="Acme")
    note = ai_review.review_job(cfg, None, job, Resume(skills=["python"]), 60.0, "Good", _TIERS)
    assert note is not None and "Strong" in note and "Good" in note


def test_review_job_none_on_agreement(monkeypatch):
    from jobscope.core import ai
    monkeypatch.setattr(ai, "score",
                        lambda *a, **k: {"score": 60.0, "sub_scores": {}, "rationale": "r"})
    cfg = load_config(None)
    job = Job(source="x", title="t", company="c")
    assert ai_review.review_job(cfg, None, job, Resume(), 60.0, "Good", _TIERS) is None
