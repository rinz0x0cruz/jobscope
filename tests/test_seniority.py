"""Tests for combined seniority detection and the asymmetric seniority score."""
from jobscope.match import _job_seniority, _seniority_score
from jobscope.model import Job, Resume


def test_job_seniority_from_title_level_and_codes():
    assert _job_seniority(Job(title="Sr Security Engineer")) == 3
    assert _job_seniority(Job(title="Security Engineer II")) == 2
    assert _job_seniority(Job(title="Security Engineer III")) == 3
    assert _job_seniority(Job(title="Staff Security Engineer")) == 4
    assert _job_seniority(Job(title="Software Engineer")) is None
    # structured job_level fills in when the title is level-less
    assert _job_seniority(Job(title="Security Engineer", job_level="Associate")) == 1
    assert _job_seniority(Job(title="Security Engineer", job_level="Director")) == 6


def test_seniority_score_is_asymmetric():
    junior = Resume(seniority="junior")
    mid_job = Job(title="Mid Security Engineer")
    senior_job = Job(title="Senior Security Engineer")
    staff_job = Job(title="Staff Security Engineer")
    # a role more senior than you scores monotonically worse
    assert _seniority_score(junior, mid_job) > _seniority_score(junior, senior_job)
    assert _seniority_score(junior, senior_job) > _seniority_score(junior, staff_job)
    # being over-qualified is only mildly penalized
    senior = Resume(seniority="senior")
    assert _seniority_score(senior, mid_job) >= 0.85


def test_target_seniority_overrides_resume():
    senior_resume = Resume(seniority="senior")
    senior_job = Job(title="Senior Security Engineer")
    # no target -> uses the resume level -> perfect match
    assert _seniority_score(senior_resume, senior_job) == 1.0
    # target "junior" -> the senior role is now clearly over the bar
    assert _seniority_score(senior_resume, senior_job, target="junior") < 0.5


def test_ai_fields_feed_seniority_and_years():
    from jobscope.match import required_experience_years
    j = Job(title="Security Engineer", ai_seniority="senior", ai_required_years=6.0)
    assert _job_seniority(j) == 3                    # AI level fills the missing signal
    assert required_experience_years(j) == 6.0       # AI years feed the experience cap
    # a plain posting with no AI signal stays ambiguous (None)
    plain = Job(title="Security Engineer")
    assert _job_seniority(plain) is None
    assert required_experience_years(plain) is None
