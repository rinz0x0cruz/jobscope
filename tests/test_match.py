from jobscope.config import DEFAULT_CONFIG
from jobscope.match import ghost_flags, score_job
from jobscope.model import Job, Resume


def _resume():
    return Resume(
        full_name="Test",
        skills=["python", "aws", "kubernetes", "iam", "threat modeling", "terraform"],
        titles=["Senior Security Engineer"],
        seniority="senior",
        years_experience=8,
        location="San Francisco, CA",
    )


def _cfg():
    c = dict(DEFAULT_CONFIG["match"])
    c["want_remote"] = True
    return c


def test_strong_beats_weak():
    r = _resume()
    strong = Job(title="Senior Security Engineer", company="A", is_remote=True,
                 salary_min=160000, salary_max=210000,
                 description="We need python, aws, kubernetes, iam and threat modeling. "
                             "Own the appsec paved road. " * 5)
    weak = Job(title="Retail Sales Associate", company="B",
               description="cold calling, quota, crm, upselling. " * 5)
    s_strong, t_strong, _ = score_job(strong, r, _cfg())
    s_weak, t_weak, _ = score_job(weak, r, _cfg())
    assert s_strong > s_weak
    assert t_strong in ("Strong", "Good")
    assert 0 <= s_weak <= 100 and 0 <= s_strong <= 100


def test_scores_bounded_and_tiered():
    r = _resume()
    j = Job(title="Security Engineer", company="C", is_remote=True,
            description="python aws iam " * 20, salary_max=180000)
    score, tier, rationale = score_job(j, r, _cfg())
    assert 0 <= score <= 100
    assert tier in ("Strong", "Good", "Stretch", "Skip")
    assert "top:" in rationale


def test_ghost_penalty_applies():
    r = _resume()
    base = Job(title="Security Engineer", company="D", is_remote=True,
               description="python aws kubernetes iam threat modeling terraform " * 10,
               salary_max=180000)
    ghost = Job(title="Security Engineer", company="D", is_remote=True,
                description="Commission only. Unlimited earning potential. Be your own boss.")
    s_base, _, _ = score_job(base, r, _cfg())
    s_ghost, _, _ = score_job(ghost, r, _cfg())
    assert ghost_flags(ghost)
    assert s_ghost < s_base


def test_missing_salary_is_neutral_not_zero():
    r = _resume()
    j = Job(title="Security Engineer", company="E", is_remote=True,
            description="python aws kubernetes iam threat modeling terraform " * 8)
    score, _, _ = score_job(j, r, _cfg())
    assert score > 40  # unknown comp shouldn't tank a good match
