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


def test_remote_scope_strict_downranks_geo_restricted_only():
    r = _resume()  # location "San Francisco, CA"
    desc = "python aws kubernetes iam threat modeling terraform " * 8
    geo = Job(title="Security Engineer", company="A", is_remote=True,
              remote_scope="Ireland", description=desc, salary_max=180000)
    off = _cfg()                                # strict off (the default)
    on = _cfg()
    on["remote_scope_strict"] = True
    s_off, _, _ = score_job(geo, r, off)
    s_on, _, _ = score_job(geo, r, on)
    assert s_on < s_off                          # geo-restricted remote is down-ranked
    # global remote is never penalized, and default behavior is unchanged
    glob = Job(title="Security Engineer", company="A", is_remote=True,
               remote_scope="global", description=desc, salary_max=180000)
    assert score_job(glob, r, on) == score_job(glob, r, off)
    # a region you actually prefer is not down-ranked even under strict
    pref = _cfg()
    pref["remote_scope_strict"] = True
    pref["prefer_locations"] = ["Remote", "Ireland"]
    assert score_job(geo, r, pref)[0] >= s_off
